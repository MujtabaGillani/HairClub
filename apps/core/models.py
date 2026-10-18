from datetime import time
from decimal import Decimal

from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

whatsapp_number_validator = RegexValidator(
    regex=r"^\d{10,15}$",
    message="Use international format with digits only, e.g. 923001234567 (no + or spaces).",
)


class TimeStampedModel(models.Model):
    """Abstract base adding creation / modification timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class SiteSettings(models.Model):
    """
    Singleton holding business configuration that the vendor can change at
    runtime without a deployment (contact details, hours, shipping fees).
    """

    CACHE_KEY = "core:site-settings"

    # Brand & contact
    business_name = models.CharField(max_length=80, default="HairClub")
    tagline = models.CharField(max_length=160, default="Non-surgical hair replacement specialists")
    whatsapp_number = models.CharField(
        max_length=15,
        default="923001234567",
        validators=[whatsapp_number_validator],
        help_text="Receives appointment requests. International format, digits only.",
    )
    phone = models.CharField(max_length=30, default="+92 300 1234567")
    email = models.EmailField(default="hello@hairclub.local")
    address = models.CharField(max_length=255, default="Main Boulevard, Gulberg III, Lahore")
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)

    # Appointments
    opening_time = models.TimeField(default=time(11, 0))
    closing_time = models.TimeField(default=time(20, 0))
    slot_interval_minutes = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(10), MaxValueValidator(240)]
    )
    slot_capacity = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="How many clients can be booked into the same time slot.",
    )
    min_booking_notice_hours = models.PositiveSmallIntegerField(
        default=2, help_text="Earliest a same-day booking can be made, in hours from now."
    )
    closed_weekdays = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Comma separated weekday numbers (0 = Monday … 6 = Sunday).",
    )

    # Shop
    standard_shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("250.00"))
    express_shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("500.00"))
    free_shipping_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("10000.00"),
        help_text="Orders at or above this subtotal ship free with standard delivery. 0 disables.",
    )
    bank_transfer_instructions = models.TextField(
        blank=True,
        default="Bank: Meezan Bank\nAccount title: HairClub\nIBAN: PK00 MEZN 0000 0000 0000 0000\n"
        "Please send the payment receipt on WhatsApp with your order number.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return f"{self.business_name} settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)

    def delete(self, *args, **kwargs):  # pragma: no cover - singleton is never deleted
        raise RuntimeError("Site settings cannot be deleted.")

    @classmethod
    def load(cls) -> "SiteSettings":
        obj = cache.get(cls.CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls.CACHE_KEY, obj, 60 * 10)
        return obj

    @property
    def closed_weekday_list(self) -> list[int]:
        return sorted({int(d) for d in self.closed_weekdays.split(",") if d.strip().isdigit()})

    @property
    def closed_weekday_names(self) -> list[str]:
        return [Weekday(d).label for d in self.closed_weekday_list if d in Weekday.values]

    @property
    def open_weekday_names(self) -> list[str]:
        closed = set(self.closed_weekday_list)
        return [label for value, label in Weekday.choices if value not in closed]
