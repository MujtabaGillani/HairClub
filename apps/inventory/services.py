"""Single entry point for changing product stock."""

from django.db import transaction

from apps.catalog.models import Product
from apps.core.http import actor

from .models import MovementReason, StockMovement


class InsufficientStock(Exception):
    def __init__(self, product: Product, requested: int):
        self.product = product
        self.requested = requested
        super().__init__(f"Only {product.stock} of “{product.name}” left in stock (requested {requested}).")


@transaction.atomic
def adjust_stock(
    product: Product | int,
    quantity_change: int,
    reason: str,
    *,
    user=None,
    reference: str = "",
    note: str = "",
) -> StockMovement:
    """
    Apply ``quantity_change`` to a product's stock under a row lock and record
    it in the ledger. Raises :class:`InsufficientStock` instead of letting
    stock go negative.
    """
    if quantity_change == 0:
        raise ValueError("Quantity change cannot be zero.")
    if reason not in MovementReason.values:
        raise ValueError(f"Unknown stock movement reason: {reason}")

    product_id = product.pk if isinstance(product, Product) else product
    locked = Product.objects.select_for_update().get(pk=product_id)
    new_stock = locked.stock + quantity_change
    if new_stock < 0:
        raise InsufficientStock(locked, abs(quantity_change))

    locked.stock = new_stock
    locked.save(update_fields=["stock", "updated_at"])
    if isinstance(product, Product):
        product.stock = new_stock

    return StockMovement.objects.create(
        product=locked,
        quantity_change=quantity_change,
        stock_after=new_stock,
        reason=reason,
        reference=reference,
        note=note[:255],
        created_by=actor(user),
    )
