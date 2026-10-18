from django.contrib import messages
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import ListView

from apps.accounts.permissions import VendorRequiredMixin
from apps.catalog.models import Category, Product
from apps.core.http import redirect_next
from apps.inventory.models import MovementReason, StockMovement
from apps.inventory.services import InsufficientStock, adjust_stock

from ..forms import StockAdjustmentForm


class InventoryListView(VendorRequiredMixin, ListView):
    template_name = "dashboard/inventory/list.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        params = self.request.GET
        qs = Product.objects.select_related("category").search(params.get("q", ""))
        if category := params.get("category"):
            qs = qs.filter(category__slug=category)
        stock = params.get("stock")
        if stock == "low":
            qs = qs.low_stock()
        elif stock == "out":
            qs = qs.out_of_stock()
        elif stock == "in":
            qs = qs.filter(stock__gt=F("low_stock_threshold"))
        return qs.order_by("stock", "name")

    def get_context_data(self, **kwargs):
        cost_per_unit = F("purchase_cost") + F("inbound_shipping_cost") + F("other_cost")
        totals = Product.objects.aggregate(
            units=Sum("stock"),
            value=Sum(
                ExpressionWrapper(
                    F("stock") * cost_per_unit, output_field=DecimalField(max_digits=14, decimal_places=2)
                )
            ),
        )
        return super().get_context_data(
            nav="inventory",
            categories=Category.objects.all(),
            total_units=totals["units"] or 0,
            stock_value=totals["value"] or 0,
            low_count=Product.objects.low_stock().count(),
            out_count=Product.objects.out_of_stock().count(),
            product_total=Product.objects.count(),
            adjustment_form=StockAdjustmentForm(),
            **kwargs,
        )


class StockAdjustView(VendorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        form = StockAdjustmentForm(request.POST, product=product)
        if not form.is_valid():
            errors = "; ".join(e for errs in form.errors.values() for e in errs)
            messages.error(request, f"Stock not changed for “{product.name}”: {errors}")
        else:
            data = form.cleaned_data
            try:
                movement = adjust_stock(
                    product, data["delta"], data["reason"], user=request.user, note=data.get("note", "")
                )
            except InsufficientStock as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    f"“{product.name}” stock {movement.quantity_change:+d} → {movement.stock_after} units.",
                )
        return redirect_next(request, "dashboard:inventory")


class StockHistoryView(VendorRequiredMixin, ListView):
    template_name = "dashboard/inventory/history.html"
    context_object_name = "movements"
    paginate_by = 30

    def get_queryset(self):
        qs = StockMovement.objects.select_related("product", "created_by")
        self.product = None
        if pk := self.kwargs.get("pk"):
            self.product = get_object_or_404(Product, pk=pk)
            qs = qs.filter(product=self.product)
        if reason := self.request.GET.get("reason"):
            qs = qs.filter(reason=reason)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(nav="inventory", product=self.product, reasons=MovementReason.choices, **kwargs)
