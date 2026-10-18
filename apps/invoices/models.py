import re
import secrets
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def generate_token() -> str:
    return secrets.token_urlsafe(24)


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    VOID = "void", "Void"


class InvoicePaymentMethod(models.TextChoices):
    NOT_SPECIFIED = "", "Not specified"
    CASH = "cash", "Cash"
    BANK = "bank_transfer", "Bank transfer"
    CARD = "card", "Card"
    OTHER = "other", "Other"


class InvoiceQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(status=InvoiceStatus.VOID)

    def standalone(self):
        """Invoices not created from a shop order or appointment (their sale isn't counted anywhere else)."""
        return self.filter(order__isnull=True, appointment__isnull=True)

    def outstanding(self):
        return self.active().filter(balance_due__gt=0).exclude(status=InvoiceStatus.DRAFT)

    def overdue(self):
        return self.outstanding().filter(due_date__lt=timezone.localdate())


class Invoice(TimeStampedModel):
    number = models.CharField(max_length=30, unique=True)
    status = models.CharField(max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT, db_index=True)

    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    delivery_date = models.DateField("delivery / service date", null=True, blank=True)
    reference = models.CharField("order reference", max_length=60, blank=True)

    # Source documents. Invoices linked to either are paperwork only for finance reporting,
    # because the order / appointment is already counted as revenue.
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    appointment = models.ForeignKey(
        "appointments.Appointment", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices"
    )

    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    billing_address = models.TextField("customer / billing address", blank=True)
    shipping_address = models.TextField("shipping / delivery address", blank=True)

    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(Decimal("0"))]
    )
    delivery_charge = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(Decimal("0"))]
    )
    tax_percent = models.DecimalField(
        "tax (%)",
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    amount_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(Decimal("0"))]
    )
    paid_on = models.DateField(
        "payment date",
        null=True,
        blank=True,
        help_text="Date of the latest payment. Standalone invoices count as revenue on this date.",
    )
    payment_method = models.CharField(max_length=20, choices=InvoicePaymentMethod.choices, blank=True, default="")

    notes = models.TextField(blank=True)
    payment_terms = models.TextField(blank=True)

    # Stored totals (recomputed on every save) so lists and reports can query them.
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, editable=False)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, editable=False)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, editable=False)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO, editable=False)

    public_token = models.CharField(max_length=64, unique=True, default=generate_token, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = InvoiceQuerySet.as_manager()

    class Meta:
        ordering = ["-invoice_date", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_paid__gte=0), name="invoice_amount_paid_non_negative"),
        ]

    def __str__(self):
        return f"{self.number} · {self.customer_name}"

    def get_absolute_url(self):
        return reverse("dashboard:invoice_detail", kwargs={"pk": self.pk})

    def get_public_url(self):
        return reverse("invoices:public", kwargs={"token": self.public_token})

    # --- Totals -------------------------------------------------------------
    def recalculate(self, items=None) -> None:
        items = list(items) if items is not None else list(self.items.all()) if self.pk else []
        self.subtotal = money(sum((item.line_total for item in items), ZERO))
        taxable = max(self.subtotal - money(self.discount_amount), ZERO)
        self.tax_amount = money(taxable * Decimal(self.tax_percent or 0) / 100)
        self.total = money(taxable + self.tax_amount + money(self.delivery_charge))
        self.balance_due = money(self.total - money(self.amount_paid))

    @property
    def payment_state(self) -> str:
        if self.status == InvoiceStatus.VOID:
            return "void"
        if self.total > 0 and self.balance_due <= 0:
            return "paid"
        if self.amount_paid > 0:
            return "partial"
        return "unpaid"

    @property
    def display_status(self) -> tuple[str, str]:
        """(label, colour) combining the workflow status with payment."""
        if self.status == InvoiceStatus.VOID:
            return "Void", "secondary"
        state = self.payment_state
        if state == "paid":
            return "Paid", "success"
        if state == "partial":
            return "Partly paid", "info"
        if self.status == InvoiceStatus.DRAFT:
            return "Draft", "light"
        if self.is_overdue:
            return "Overdue", "danger"
        return "Sent", "warning"

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.due_date
            and self.balance_due > 0
            and self.status == InvoiceStatus.SENT
            and self.due_date < timezone.localdate()
        )

    @property
    def counts_as_revenue(self) -> bool:
        return self.order_id is None and self.appointment_id is None and self.status != InvoiceStatus.VOID

    @property
    def is_editable(self) -> bool:
        return self.status != InvoiceStatus.VOID

    @staticmethod
    def next_number() -> str:
        """INV-0001, INV-0002 … based on the highest numeric suffix used so far."""
        highest = 0
        for number in Invoice.objects.filter(number__startswith="INV-").values_list("number", flat=True):
            match = re.fullmatch(r"INV-(\d+)", number)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"INV-{highest + 1:04d}"


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("1"), validators=[MinValueValidator(Decimal("0.01"))]
    )
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(Decimal("0"))]
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "pk"]

    def __str__(self):
        return f"{self.quantity} × {self.description}"

    @property
    def line_total(self) -> Decimal:
        return money(Decimal(self.quantity or 0) * Decimal(self.unit_price or 0))

    @property
    def quantity_display(self) -> str:
        q = Decimal(self.quantity or 0)
        return f"{q:.0f}" if q == q.to_integral_value() else f"{q.normalize()}"
