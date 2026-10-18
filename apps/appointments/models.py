import secrets
from datetime import datetime

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


class ServiceQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Service(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    short_description = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    starting_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Leave empty to show 'Price on consultation'.",
    )
    icon = models.CharField(max_length=40, default="scissors", help_text="Bootstrap icon name.")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    objects = ServiceQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)

    def get_book_url(self):
        return f"{reverse('appointments:book')}?service={self.slug}"


class AppointmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    NO_SHOW = "no_show", "No-show"


APPOINTMENT_TRANSITIONS: dict[str, set[str]] = {
    AppointmentStatus.PENDING: {AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED},
    AppointmentStatus.CONFIRMED: {AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW},
    AppointmentStatus.COMPLETED: set(),
    AppointmentStatus.CANCELLED: set(),
    AppointmentStatus.NO_SHOW: set(),
}

# Statuses that occupy a time slot.
BLOCKING_STATUSES = (AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED)


def generate_reference() -> str:
    return f"APT-{secrets.token_hex(3).upper()}"


class AppointmentQuerySet(models.QuerySet):
    def blocking(self):
        return self.filter(status__in=BLOCKING_STATUSES)

    def upcoming(self):
        now = timezone.localtime()
        return self.filter(
            Q(date__gt=now.date()) | Q(date=now.date(), time__gte=now.time()),
            status__in=BLOCKING_STATUSES,
        ).order_by("date", "time")

    def for_user(self, user):
        return self.filter(Q(user=user) | Q(user__isnull=True, email__iexact=user.email))


class Appointment(TimeStampedModel):
    reference = models.CharField(max_length=12, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="appointments"
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="appointments")
    date = models.DateField()
    time = models.TimeField()
    notes = models.TextField(blank=True, max_length=1000)

    status = models.CharField(
        max_length=20, choices=AppointmentStatus.choices, default=AppointmentStatus.PENDING, db_index=True
    )
    vendor_note = models.TextField("internal note", blank=True)
    amount_charged = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="What the client paid; recorded when the appointment is completed (service revenue).",
    )
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)

    objects = AppointmentQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "-time"]
        indexes = [models.Index(fields=["date", "time"])]

    def __str__(self):
        return f"{self.reference} · {self.full_name} · {self.date} {self.time:%H:%M}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generate_reference()
            while Appointment.objects.filter(reference=self.reference).exists():
                self.reference = generate_reference()
        super().save(*args, **kwargs)

    @property
    def starts_at(self) -> datetime:
        return timezone.make_aware(datetime.combine(self.date, self.time))

    @property
    def is_past(self) -> bool:
        return self.starts_at < timezone.now()

    @property
    def can_complete(self) -> bool:
        return AppointmentStatus.COMPLETED in APPOINTMENT_TRANSITIONS.get(self.status, set())

    @property
    def allowed_transitions(self) -> list[tuple[str, str]]:
        allowed = APPOINTMENT_TRANSITIONS.get(self.status, set())
        return [(value, label) for value, label in AppointmentStatus.choices if value in allowed]
