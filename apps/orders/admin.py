from django.contrib import admin

from .models import Order, OrderEvent, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "sku", "unit_price", "quantity", "line_total")
    can_delete = False


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ("status", "note", "created_by", "created_at")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "full_name", "email", "total", "status", "payment_status", "created_at")
    list_filter = ("status", "payment_status", "payment_method", "shipping_method")
    search_fields = ("number", "full_name", "email", "phone")
    readonly_fields = ("number", "subtotal", "shipping_cost", "total", "created_at", "updated_at")
    inlines = [OrderItemInline, OrderEventInline]
    date_hierarchy = "created_at"
