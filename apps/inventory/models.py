from django.conf import settings
from django.db import models


class MovementReason(models.TextChoices):
    INITIAL = "initial", "Initial stock"
    RESTOCK = "restock", "Restock / purchase"
    SALE = "sale", "Sale (order)"
    ORDER_CANCELLED = "order_cancelled", "Order cancelled (returned to stock)"
    RETURN = "return", "Customer return"
    DAMAGED = "damaged", "Damaged / expired"
    CORRECTION = "correction", "Stock count correction"


class StockMovement(models.Model):
    """
    Append-only ledger of every stock change. ``Product.stock`` is the current
    balance; this table explains how it got there.
    """

    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="stock_movements")
    quantity_change = models.IntegerField()
    stock_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=30, choices=MovementReason.choices)
    reference = models.CharField(max_length=40, blank=True, help_text="Order number or supplier invoice.")
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.product} {self.quantity_change:+d} ({self.get_reason_display()})"
