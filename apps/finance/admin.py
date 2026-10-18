from django.contrib import admin

from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "description", "paid_to", "amount", "payment_method")
    list_filter = ("category", "payment_method")
    search_fields = ("description", "paid_to", "notes")
    date_hierarchy = "date"
    list_select_related = ("category",)
