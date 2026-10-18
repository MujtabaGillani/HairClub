"""Order domain logic: pricing, placement, and status workflow."""

import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.http import actor
from apps.core.models import SiteSettings
from apps.inventory.models import MovementReason
from apps.inventory.services import InsufficientStock, adjust_stock

from .models import (
    ORDER_TRANSITIONS,
    Order,
    OrderEvent,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ShippingMethod,
)

logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    """Raised when an order cannot be placed; the message is safe to show to shoppers."""


class InvalidTransition(Exception):
    pass


def calculate_shipping(subtotal: Decimal, method: str, site: SiteSettings | None = None) -> Decimal:
    site = site or SiteSettings.load()
    if method == ShippingMethod.PICKUP or subtotal <= 0:
        return Decimal("0.00")
    if method == ShippingMethod.EXPRESS:
        return site.express_shipping_fee
    threshold = site.free_shipping_threshold
    if threshold and subtotal >= threshold:
        return Decimal("0.00")
    return site.standard_shipping_fee


def place_order(*, cart, data: dict, user=None) -> Order:
    """
    Turn the cart into an order atomically.

    Product rows are locked in a consistent order (by PK) to avoid deadlocks;
    prices are re-read from the database, and stock is decremented through the
    inventory ledger. Any failure rolls the whole order back.
    """
    if cart.is_empty or not cart.lines:
        raise CheckoutError("Your cart is empty.")

    requested = {line.product.pk: line.quantity for line in cart.lines}

    with transaction.atomic():
        products = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=requested.keys()).order_by("pk")}
        subtotal = Decimal("0.00")
        snapshot = []
        for pid, qty in requested.items():
            product = products.get(pid)
            if product is None or not product.is_purchasable:
                raise CheckoutError("An item in your cart is no longer available. Please review your cart.")
            if product.stock < qty:
                raise CheckoutError(f"Only {product.stock} of “{product.name}” left in stock. Please update your cart.")
            unit_price = product.final_price
            subtotal += unit_price * qty
            snapshot.append((product, qty, unit_price))

        shipping_method = data["shipping_method"]
        shipping_cost = calculate_shipping(subtotal, shipping_method)

        order = Order.objects.create(
            user=actor(user),
            full_name=data["full_name"],
            email=data["email"],
            phone=data["phone"],
            address_line1=data.get("address_line1", ""),
            address_line2=data.get("address_line2", ""),
            city=data.get("city", ""),
            province=data.get("province", ""),
            postal_code=data.get("postal_code", ""),
            notes=data.get("notes", ""),
            shipping_method=shipping_method,
            payment_method=data["payment_method"],
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            total=subtotal + shipping_cost,
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    product=product,
                    product_name=product.name,
                    sku=product.sku,
                    unit_price=unit_price,
                    quantity=qty,
                    line_total=unit_price * qty,
                    unit_cost=product.unit_cost,
                )
                for product, qty, unit_price in snapshot
            ]
        )
        try:
            for product, qty, _ in snapshot:
                adjust_stock(product.pk, -qty, MovementReason.SALE, user=user, reference=order.number)
        except InsufficientStock as exc:  # pragma: no cover - guarded by the lock above
            raise CheckoutError(str(exc)) from exc

        OrderEvent.objects.create(order=order, status=OrderStatus.PENDING, note="Order placed")
        transaction.on_commit(lambda: send_order_confirmation(order.pk))

    cart.clear()
    logger.info("Order %s placed (%s items, total %s)", order.number, len(snapshot), order.total)
    return order


@transaction.atomic
def change_order_status(order: Order, new_status: str, *, user=None, note: str = "") -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if new_status not in ORDER_TRANSITIONS.get(order.status, set()):
        raise InvalidTransition(
            f"Cannot change order from {order.get_status_display()} to {OrderStatus(new_status).label}."
        )

    if new_status == OrderStatus.CANCELLED:
        for item in order.items.select_related("product"):
            if item.product_id:
                adjust_stock(
                    item.product_id, item.quantity, MovementReason.ORDER_CANCELLED, user=user, reference=order.number
                )
        if order.payment_status == PaymentStatus.PAID:
            note = f"{note} (refund required)".strip()

    if new_status == OrderStatus.DELIVERED:
        order.delivered_at = timezone.now()  # revenue is recognised on this date
        if order.payment_method == PaymentMethod.COD:
            order.payment_status = PaymentStatus.PAID

    order.status = new_status
    order.save(update_fields=["status", "payment_status", "delivered_at", "updated_at"])
    OrderEvent.objects.create(order=order, status=new_status, note=note[:255], created_by=actor(user))
    return order


@transaction.atomic
def mark_order_paid(order: Order, *, user=None) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == OrderStatus.CANCELLED:
        raise InvalidTransition("A cancelled order cannot be marked as paid.")
    if order.payment_status != PaymentStatus.PAID:
        order.payment_status = PaymentStatus.PAID
        order.save(update_fields=["payment_status", "updated_at"])
        OrderEvent.objects.create(order=order, status=order.status, note="Payment received", created_by=actor(user))
    return order


def send_order_confirmation(order_id: int) -> None:
    order = Order.objects.prefetch_related("items").get(pk=order_id)
    site = SiteSettings.load()
    context = {"order": order, "site": site, "currency": settings.CURRENCY_SYMBOL}
    try:
        send_mail(
            subject=f"{site.business_name}: order {order.number} received",
            message=render_to_string("orders/email/order_confirmation.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
        )
    except Exception:  # email failure must never break checkout
        logger.exception("Could not send confirmation email for order %s", order.number)
