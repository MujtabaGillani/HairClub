from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class ExpenseCategoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=60, unique=True)
    icon = models.CharField(max_length=40, default="receipt", help_text="Bootstrap icon name.")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    objects = ExpenseCategoryQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "expense categories"

    def __str__(self):
        return self.name


class ExpensePaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    BANK = "bank", "Bank transfer"
    CARD = "card", "Card"
    OTHER = "other", "Other"


class Expense(TimeStampedModel):
    """Operating expense: salaries, rent, utilities, food, entertainment, etc.
    Stock purchases are *not* recorded here; their cost is counted as cost of
    goods sold when the product is sold."""

    date = models.DateField(default=timezone.localdate, db_index=True)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    description = models.CharField(max_length=200)
    paid_to = models.CharField(max_length=120, blank=True, help_text="Employee, landlord, supplier…")
    payment_method = models.CharField(
        max_length=10, choices=ExpensePaymentMethod.choices, default=ExpensePaymentMethod.CASH
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-date", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="expense_amount_positive")]

    def __str__(self):
        return f"{self.date:%d %b %Y} · {self.category} · {self.amount}"
