from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.cart.services import Cart
from apps.core.models import SiteSettings
from apps.core.whatsapp import build_whatsapp_url

from .forms import CheckoutForm, OrderLookupForm
from .models import Order, OrderStatus, ShippingMethod
from .services import CheckoutError, InvalidTransition, calculate_shipping, change_order_status, place_order

GUEST_ORDERS_SESSION_KEY = "guest_orders"


def _remember_order(request, order: Order) -> None:
    numbers = request.session.get(GUEST_ORDERS_SESSION_KEY, [])
    if order.number not in numbers:
        request.session[GUEST_ORDERS_SESSION_KEY] = (numbers + [order.number])[-20:]


def _get_accessible_order(request, number: str) -> Order:
    """Owners, vendors, or the browser session that placed / looked up the order may view it."""
    order = get_object_or_404(Order.objects.prefetch_related("items", "events"), number=number)
    user = request.user
    if user.is_authenticated and (order.user_id == user.pk or user.is_vendor):
        return order
    if number in request.session.get(GUEST_ORDERS_SESSION_KEY, []):
        return order
    raise Http404("Order not found")


def _initial_checkout_data(request) -> dict:
    user = request.user
    if not user.is_authenticated:
        return {}
    initial = {"full_name": user.get_full_name(), "email": user.email, "phone": user.phone}
    last = Order.objects.filter(user=user).first()
    if last:
        for field in ("phone", "address_line1", "address_line2", "city", "province", "postal_code"):
            initial[field] = initial.get(field) or getattr(last, field)
    return initial


def checkout(request):
    cart = Cart(request)
    if cart.is_empty or not cart.lines:
        messages.info(request, "Your cart is empty.")
        return redirect("cart:detail")

    site = SiteSettings.load()
    form = CheckoutForm(request.POST or None, initial=_initial_checkout_data(request))
    if request.method == "POST" and form.is_valid():
        try:
            order = place_order(cart=cart, data=form.cleaned_data, user=request.user)
        except CheckoutError as exc:
            messages.error(request, str(exc))
            return redirect("cart:detail")
        _remember_order(request, order)
        return redirect("orders:confirmation", number=order.number)

    subtotal = cart.subtotal
    shipping_options = [
        {"value": value, "label": label, "cost": calculate_shipping(subtotal, value, site)}
        for value, label in ShippingMethod.choices
    ]
    selected = form["shipping_method"].value() or ShippingMethod.STANDARD
    shipping_cost = calculate_shipping(subtotal, selected, site)
    return render(
        request,
        "orders/checkout.html",
        {
            "form": form,
            "cart": cart,
            "shipping_options": shipping_options,
            "shipping_cost": shipping_cost,
            "total": subtotal + shipping_cost,
        },
    )


def order_confirmation(request, number):
    order = _get_accessible_order(request, number)
    site = SiteSettings.load()
    message = (
        f"Hi {site.business_name}, I just placed order {order.number} "
        f"({order.item_count} item(s), total {order.total})."
    )
    return render(
        request,
        "orders/confirmation.html",
        {"order": order, "whatsapp_url": build_whatsapp_url(site.whatsapp_number, message)},
    )


def order_detail(request, number):
    order = _get_accessible_order(request, number)
    return render(request, "orders/order_detail.html", {"order": order})


@require_POST
def order_cancel(request, number):
    order = _get_accessible_order(request, number)
    if not order.can_be_cancelled_by_customer:
        messages.error(request, "This order can no longer be cancelled online. Please contact us.")
        return redirect(order.get_absolute_url())
    try:
        change_order_status(order, OrderStatus.CANCELLED, user=request.user, note="Cancelled by customer")
    except InvalidTransition as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Order {order.number} has been cancelled.")
    return redirect(order.get_absolute_url())


def order_lookup(request):
    form = OrderLookupForm(request.GET or None)
    if request.GET and form.is_valid():
        order = Order.objects.filter(
            number=form.cleaned_data["number"], email__iexact=form.cleaned_data["email"]
        ).first()
        if order:
            _remember_order(request, order)
            return redirect(order.get_absolute_url())
        form.add_error(None, "We couldn't find an order with those details.")
    return render(request, "orders/lookup.html", {"form": form})
