from django.contrib import admin

from .models import Appointment, Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "duration_minutes", "starting_price", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "phone", "service", "date", "time", "status")
    list_filter = ("status", "service", "date")
    search_fields = ("reference", "full_name", "phone", "email")
    readonly_fields = ("reference", "created_at", "updated_at", "status_changed_at")
    date_hierarchy = "date"
    list_select_related = ("service",)
