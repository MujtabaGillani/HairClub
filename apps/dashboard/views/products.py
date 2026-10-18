from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.accounts.permissions import VendorRequiredMixin
from apps.catalog.models import Category, Product
from apps.core.http import redirect_next
from apps.inventory.models import MovementReason
from apps.inventory.services import adjust_stock

from ..forms import ProductForm
from ..sorting import SortableListMixin

TOGGLEABLE_FIELDS = {"is_active": "Published", "show_price": "Price visibility", "is_featured": "Featured"}


class ProductListView(VendorRequiredMixin, SortableListMixin, ListView):
    sort_options = {
        "newest": ("Newest first", ["-created_at"]),
        "oldest": ("Oldest first", ["created_at"]),
        "name": ("Name A–Z", ["name"]),
        "name_desc": ("Name Z–A", ["-name"]),
        "price_desc": ("Price: high to low", ["-price"]),
        "price_asc": ("Price: low to high", ["price"]),
        "stock_asc": ("Stock: low to high", ["stock", "name"]),
        "stock_desc": ("Stock: high to low", ["-stock", "name"]),
    }
    default_sort = "newest"

    template_name = "dashboard/products/list.html"
    context_object_name = "products"
    paginate_by = 15

    def get_queryset(self):
        params = self.request.GET
        qs = Product.objects.with_images().search(params.get("q", ""))
        if category := params.get("category"):
            qs = qs.filter(category__slug=category)
        status = params.get("status")
        if status == "published":
            qs = qs.filter(is_active=True)
        elif status == "draft":
            qs = qs.filter(is_active=False)
        elif status == "hidden_price":
            qs = qs.filter(show_price=False)
        elif status == "on_sale":
            qs = qs.filter(discount_percent__gt=0)
        return self.apply_sort(qs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(nav="products", categories=Category.objects.all(), **kwargs)


class ProductFormMixin(VendorRequiredMixin):
    model = Product
    form_class = ProductForm
    template_name = "dashboard/products/form.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            nav="products",
            min_images=settings.PRODUCT_MIN_IMAGES,
            max_images=settings.PRODUCT_MAX_IMAGES,
            **kwargs,
        )

    def get_success_url(self):
        if "save_and_add" in self.request.POST:
            return reverse("dashboard:product_create")
        return reverse("dashboard:product_list")


class ProductCreateView(ProductFormMixin, CreateView):
    @transaction.atomic
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.stock = 0
        self.object = form.save()
        form.save_images(self.object)
        opening = form.cleaned_data.get("initial_stock") or 0
        if opening:
            adjust_stock(self.object, opening, MovementReason.INITIAL, user=self.request.user, note="Opening stock")
        messages.success(self.request, f"“{self.object.name}” has been created.")
        return redirect(self.get_success_url())


class ProductUpdateView(ProductFormMixin, UpdateView):
    @transaction.atomic
    def form_valid(self, form):
        self.object = form.save()
        form.save_images(self.object)
        messages.success(self.request, f"“{self.object.name}” has been updated.")
        return redirect(self.get_success_url())


class ProductDeleteView(VendorRequiredMixin, DeleteView):
    model = Product
    template_name = "dashboard/products/confirm_delete.html"
    context_object_name = "product"

    def get_context_data(self, **kwargs):
        return super().get_context_data(nav="products", order_count=self.object.order_items.count(), **kwargs)

    def form_valid(self, form):
        name = self.object.name
        self.object.delete()
        messages.success(self.request, f"“{name}” has been deleted.")
        return redirect("dashboard:product_list")


class ProductToggleView(VendorRequiredMixin, View):
    """Flip a boolean flag (published / show price / featured) from the product list."""

    http_method_names = ["post"]

    def post(self, request, pk, field):
        if field not in TOGGLEABLE_FIELDS:
            messages.error(request, "Unknown setting.")
            return redirect("dashboard:product_list")
        product = get_object_or_404(Product, pk=pk)
        setattr(product, field, not getattr(product, field))
        product.save(update_fields=[field, "updated_at"])
        state = "on" if getattr(product, field) else "off"
        messages.success(request, f"{TOGGLEABLE_FIELDS[field]} turned {state} for “{product.name}”.")
        return redirect_next(request, "dashboard:product_list")
