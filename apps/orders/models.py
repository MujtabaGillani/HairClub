import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    PROCESSING = "processing", "Processing"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


# Allowed workflow transitions. Anything not listed is rejected.
ORDER_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PROCESSING, OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


class PaymentMethod(models.TextChoices):
    COD = "cod", "Cash on delivery"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"


class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PAID = "paid", "Paid"
    REFUNDED = "refunded", "Refunded"


class ShippingMethod(models.TextChoices):
    STANDARD = "standard", "Standard delivery (3–5 working days)"
    EXPRESS = "express", "Express delivery (1–2 working days)"
    PICKUP = "pickup", "Collect from salon"


def generate_order_number() -> str:
    return f"HC{timezone.localdate():%y%m%d}-{secrets.token_hex(3).upper()}"


class OrderQuerySet(models.QuerySet):
    def open(self):
        return self.exclude(status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED])

    def revenue(self):
        """Orders that count towards sales figures."""
        return self.exclude(status=OrderStatus.CANCELLED)


class Order(TimeStampedModel):
    number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )

    # Contact
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30)

    # Shipping address
    address_line1 = models.CharField("address", max_length=255, blank=True)
    address_line2 = models.CharField("apartment, suite, etc.", max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=60, default="Pakistan")
    notes = models.TextField("order notes", blank=True)

    # Money
    shipping_method = models.CharField(max_length=20, choices=ShippingMethod.choices, default=ShippingMethod.STANDARD)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2)

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.COD)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING, db_index=True)
    tracking_number = models.CharField(max_length=60, blank=True)
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Set when the order is delivered; revenue is booked on this date.",
    )

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.number}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = generate_order_number()
            while Order.objects.filter(number=self.number).exists():
                self.number = generate_order_number()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("orders:detail", kwargs={"number": self.number})

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.all())

    @property
    def allowed_transitions(self) -> list[tuple[str, str]]:
        allowed = ORDER_TRANSITIONS.get(self.status, set())
        return [(value, label) for value, label in OrderStatus.choices if value in allowed]

    @property
    def can_be_cancelled_by_customer(self) -> bool:
        return self.status == OrderStatus.PENDING

    @property
    def shipping_address(self) -> str:
        parts = [self.address_line1, self.address_line2, self.city, self.province, self.postal_code, self.country]
        return ", ".join(p for p in parts if p)

    @property
    def is_pickup(self) -> bool:
        return self.shipping_method == ShippingMethod.PICKUP

    # --- Vendor-only profitability -------------------------------------------
    @property
    def cost_of_goods(self) -> Decimal:
        return sum((item.line_cost for item in self.items.all()), Decimal("0.00"))

    @property
    def gross_profit(self) -> Decimal:
        """Product sales minus their cost (shipping charged to the customer excluded)."""
        return self.subtotal - self.cost_of_goods


class OrderItem(models.Model):
    """Snapshot of a product at purchase time; survives product edits or deletion."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="order_items"
    )
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=40)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), help_text="Product landed cost at the time of sale."
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"

    @property
    def line_cost(self) -> Decimal:
        return self.unit_cost * self.quantity

    @property
    def line_profit(self) -> Decimal:
        return self.line_total - self.line_cost


class OrderEvent(models.Model):
    """Audit trail of status changes and notes on an order."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=20, choices=OrderStatus.choices)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.order.number}: {self.get_status_display()}"
