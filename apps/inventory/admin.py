from django.contrib import admin

from .models import StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "product", "quantity_change", "stock_after", "reason", "reference", "created_by")
    list_filter = ("reason",)
    search_fields = ("product__name", "product__sku", "reference")
    list_select_related = ("product", "created_by")

    def has_change_permission(self, request, obj=None):
        return False  # ledger is append-only

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
