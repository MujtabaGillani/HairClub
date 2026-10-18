"""
Session-backed shopping cart.

Only product IDs and quantities are stored in the session. Prices, names and
availability are always re-read from the database, so a tampered session or a
price change can never lead to a wrong charge.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from apps.catalog.models import Product


@dataclass(frozen=True)
class CartLine:
    product: Product
    quantity: int

    @property
    def unit_price(self) -> Decimal:
        return self.product.final_price

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def max_quantity(self) -> int:
        return min(self.product.stock, settings.CART_MAX_QUANTITY_PER_ITEM)


class Cart:
    def __init__(self, request):
        self.session = request.session
        raw = self.session.get(settings.CART_SESSION_KEY) or {}
        self._items: dict[str, int] = {
            str(pid): int(qty) for pid, qty in raw.items() if str(pid).isdigit() and str(qty).lstrip("-").isdigit()
        }
        self._lines: list[CartLine] | None = None

    # --- Mutations ---------------------------------------------------------
    def add(self, product: Product, quantity: int = 1, *, replace: bool = False) -> int:
        """Add (or set) a quantity, clamped to available stock. Returns the final quantity."""
        key = str(product.pk)
        current = 0 if replace else self._items.get(key, 0)
        limit = min(product.stock, settings.CART_MAX_QUANTITY_PER_ITEM)
        new_quantity = max(0, min(current + quantity, limit))
        if new_quantity == 0:
            self._items.pop(key, None)
        else:
            self._items[key] = new_quantity
        self._save()
        return new_quantity

    def remove(self, product_id: int) -> None:
        if self._items.pop(str(product_id), None) is not None:
            self._save()

    def clear(self) -> None:
        self._items = {}
        self._save()

    def _save(self) -> None:
        self.session[settings.CART_SESSION_KEY] = self._items
        self.session.modified = True
        self._lines = None

    # --- Queries -----------------------------------------------------------
    def quantity_of(self, product_id: int) -> int:
        return self._items.get(str(product_id), 0)

    @property
    def lines(self) -> list[CartLine]:
        """Cart lines for purchasable products; silently drops anything no longer for sale."""
        if self._lines is None:
            products = Product.objects.visible().with_images().in_bulk([int(pid) for pid in self._items])
            lines, changed = [], False
            for pid, qty in list(self._items.items()):
                product = products.get(int(pid))
                if product is None or not product.is_purchasable:
                    self._items.pop(pid)
                    changed = True
                    continue
                allowed = min(qty, product.stock, settings.CART_MAX_QUANTITY_PER_ITEM)
                if allowed != qty:
                    self._items[pid] = allowed
                    changed = True
                lines.append(CartLine(product=product, quantity=allowed))
            if changed:
                self.session[settings.CART_SESSION_KEY] = self._items
                self.session.modified = True
            self._lines = lines
        return self._lines

    def __iter__(self):
        return iter(self.lines)

    def __len__(self) -> int:
        return sum(self._items.values())

    @property
    def is_empty(self) -> bool:
        return not self._items

    @property
    def subtotal(self) -> Decimal:
        return sum((line.line_total for line in self.lines), Decimal("0.00"))
