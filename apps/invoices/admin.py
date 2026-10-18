from django.contrib import admin

from .models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "customer_name", "invoice_date", "total", "amount_paid", "balance_due", "status")
    list_filter = ("status",)
    search_fields = ("number", "customer_name", "phone", "email", "reference")
    readonly_fields = ("subtotal", "tax_amount", "total", "balance_due", "public_token", "sent_at")
    inlines = [InvoiceItemInline]
    date_hierarchy = "invoice_date"
