from django.contrib import admin

from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Brand & contact", {"fields": ("business_name", "tagline", "whatsapp_number", "phone", "email", "address")}),
        ("Social", {"fields": ("instagram_url", "facebook_url", "tiktok_url")}),
        (
            "Appointments",
            {
                "fields": (
                    "opening_time",
                    "closing_time",
                    "slot_interval_minutes",
                    "slot_capacity",
                    "min_booking_notice_hours",
                    "closed_weekdays",
                )
            },
        ),
        (
            "Shop",
            {
                "fields": (
                    "standard_shipping_fee",
                    "express_shipping_fee",
                    "free_shipping_threshold",
                    "bank_transfer_instructions",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
