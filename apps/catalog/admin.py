from django.contrib import admin

from .models import Category, Product, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    max_num = 7


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "price", "discount_percent", "stock", "show_price", "is_active")
    list_filter = ("is_active", "show_price", "is_featured", "category")
    search_fields = ("name", "sku", "brand")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("stock", "created_by", "created_at", "updated_at")
    inlines = [ProductImageInline]
    list_select_related = ("category",)
