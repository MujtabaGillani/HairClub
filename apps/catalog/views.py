from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from apps.core.models import SiteSettings
from apps.core.whatsapp import build_whatsapp_url

from .models import Category, Product

SORT_OPTIONS = {
    "newest": ("Newest", ["-created_at"]),
    "price_asc": ("Price: low to high", ["effective_price", "name"]),
    "price_desc": ("Price: high to low", ["-effective_price", "name"]),
    "name": ("Name: A–Z", ["name"]),
}


class ProductListView(ListView):
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        params = self.request.GET
        qs = (
            Product.objects.visible()
            .with_images()
            .annotate(
                effective_price=ExpressionWrapper(
                    F("price") * (Decimal(100) - F("discount_percent")) / Decimal(100),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .search(params.get("q", ""))
        )

        self.category = None
        if slug := params.get("category"):
            self.category = Category.objects.active().filter(slug=slug).first()
            if self.category:
                qs = qs.filter(category=self.category)

        if params.get("in_stock") == "1":
            qs = qs.filter(stock__gt=0)
        if params.get("on_sale") == "1":
            qs = qs.filter(discount_percent__gt=0)

        self.sort = params.get("sort") if params.get("sort") in SORT_OPTIONS else "newest"
        return qs.order_by(*SORT_OPTIONS[self.sort][1])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            categories=Category.objects.active(),
            current_category=self.category,
            sort=self.sort,
            sort_options={key: label for key, (label, _) in SORT_OPTIONS.items()},
            query=self.request.GET.get("q", "").strip(),
        )
        return context


class ProductDetailView(DetailView):
    template_name = "catalog/product_detail.html"
    context_object_name = "product"

    def get_object(self, queryset=None):
        return get_object_or_404(Product.objects.visible().with_images(), slug=self.kwargs["slug"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        site = SiteSettings.load()
        context["related_products"] = (
            Product.objects.visible().with_images().filter(category=product.category).exclude(pk=product.pk)[:4]
        )
        context["enquiry_url"] = build_whatsapp_url(
            site.whatsapp_number,
            f"Hi {site.business_name}, I'd like to know more about “{product.name}” (SKU {product.sku}).\n"
            f"{self.request.build_absolute_uri(product.get_absolute_url())}",
        )
        context["max_quantity"] = min(product.stock, 20)
        return context
