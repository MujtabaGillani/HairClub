"""Appointment scheduling rules and WhatsApp message composition."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.core.http import actor
from apps.core.models import SiteSettings
from apps.core.whatsapp import build_whatsapp_url

from .models import APPOINTMENT_TRANSITIONS, Appointment, AppointmentStatus


class InvalidTransition(Exception):
    pass


class SlotUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Slot:
    time: time
    remaining: int

    @property
    def value(self) -> str:
        return self.time.strftime("%H:%M")

    @property
    def label(self) -> str:
        return self.time.strftime("%I:%M %p").lstrip("0")

    @property
    def available(self) -> bool:
        return self.remaining > 0


def booking_window(site: SiteSettings | None = None) -> tuple[date, date]:
    today = timezone.localdate()
    return today, today + timedelta(days=settings.APPOINTMENT_MAX_DAYS_AHEAD)


def is_open_on(day: date, site: SiteSettings) -> bool:
    return day.weekday() not in site.closed_weekday_list


def generate_slot_times(site: SiteSettings) -> list[time]:
    times, step = [], timedelta(minutes=site.slot_interval_minutes)
    cursor = datetime.combine(date.today(), site.opening_time)
    end = datetime.combine(date.today(), site.closing_time)
    while cursor < end:
        times.append(cursor.time())
        cursor += step
    return times


def get_slots(day: date, site: SiteSettings | None = None) -> list[Slot]:
    """Every slot for ``day`` with remaining capacity. Empty if the salon is closed."""
    site = site or SiteSettings.load()
    first, last = booking_window(site)
    if not (first <= day <= last) or not is_open_on(day, site):
        return []

    booked = dict(
        Appointment.objects.blocking().filter(date=day).values_list("time").annotate(n=Count("id")).order_by()
    )
    earliest = timezone.localtime() + timedelta(hours=site.min_booking_notice_hours)
    slots = []
    for slot_time in generate_slot_times(site):
        starts = timezone.make_aware(datetime.combine(day, slot_time))
        if starts < earliest:
            continue
        slots.append(Slot(time=slot_time, remaining=max(site.slot_capacity - booked.get(slot_time, 0), 0)))
    return slots


def is_slot_available(day: date, slot_time: time, site: SiteSettings | None = None) -> bool:
    return any(s.time == slot_time and s.available for s in get_slots(day, site))


@transaction.atomic
def create_appointment(*, data: dict, user=None) -> Appointment:
    """
    Book a slot. The site-settings row is locked as a lightweight mutex so two
    concurrent requests cannot both take the last place in a slot.
    """
    site = SiteSettings.objects.select_for_update().get(pk=SiteSettings.load().pk)
    if not is_slot_available(data["date"], data["time"], site):
        raise SlotUnavailable("Sorry, that time was just taken. Please choose another slot.")
    return Appointment.objects.create(
        user=actor(user),
        full_name=data["full_name"],
        phone=data["phone"],
        email=data.get("email", ""),
        service=data["service"],
        date=data["date"],
        time=data["time"],
        notes=data.get("notes", ""),
    )


def vendor_whatsapp_message(appointment: Appointment, site: SiteSettings) -> str:
    lines = [
        f"*New appointment request* · {appointment.reference}",
        "",
        f"*Name:* {appointment.full_name}",
        f"*Phone:* {appointment.phone}",
    ]
    if appointment.email:
        lines.append(f"*Email:* {appointment.email}")
    lines += [
        f"*Service:* {appointment.service.name}",
        f"*Date:* {appointment.date:%A, %d %B %Y}",
        f"*Time:* {appointment.time:%I:%M %p}",
    ]
    if appointment.notes:
        lines += ["", f"*Notes:* {appointment.notes}"]
    lines += ["", "Please confirm my appointment. Thank you!"]
    return "\n".join(lines)


def vendor_whatsapp_url(appointment: Appointment, site: SiteSettings | None = None) -> str:
    site = site or SiteSettings.load()
    return build_whatsapp_url(site.whatsapp_number, vendor_whatsapp_message(appointment, site))


def customer_whatsapp_url(appointment: Appointment, site: SiteSettings | None = None) -> str:
    """Pre-filled message the vendor can send to the customer after a status change."""
    site = site or SiteSettings.load()
    when = f"{appointment.date:%A, %d %B} at {appointment.time:%I:%M %p}"
    messages = {
        AppointmentStatus.CONFIRMED: (
            f"Hi {appointment.full_name}, your {appointment.service.name} appointment at "
            f"{site.business_name} is *confirmed* for {when}. Ref: {appointment.reference}. "
            f"Address: {site.address}. See you soon!"
        ),
        AppointmentStatus.CANCELLED: (
            f"Hi {appointment.full_name}, unfortunately we're unable to keep your {appointment.service.name} "
            f"appointment on {when} (Ref: {appointment.reference}). Reply here and we'll find another time."
        ),
    }
    text = messages.get(
        appointment.status,
        f"Hi {appointment.full_name}, this is {site.business_name} about your appointment {appointment.reference}.",
    )
    return build_whatsapp_url(appointment.phone, text)


@transaction.atomic
def change_appointment_status(
    appointment: Appointment,
    new_status: str,
    *,
    user=None,
    note: str = "",
    amount_charged: Decimal | None = None,
) -> Appointment:
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if new_status not in APPOINTMENT_TRANSITIONS.get(appointment.status, set()):
        raise InvalidTransition(
            f"Cannot change appointment from {appointment.get_status_display()} "
            f"to {AppointmentStatus(new_status).label}."
        )
    if new_status == AppointmentStatus.COMPLETED and (amount_charged is None or amount_charged < 0):
        raise InvalidTransition("Enter the amount charged to complete the appointment (0 if it was free).")
    appointment.status = new_status
    appointment.handled_by = actor(user)
    appointment.status_changed_at = timezone.now()
    fields = ["status", "handled_by", "status_changed_at", "updated_at"]
    if new_status == AppointmentStatus.COMPLETED:
        appointment.amount_charged = amount_charged
        fields.append("amount_charged")
    if note:
        stamp = timezone.localtime().strftime("%d %b %H:%M")
        appointment.vendor_note = f"{appointment.vendor_note}\n[{stamp}] {note}".strip()
        fields.append("vendor_note")
    appointment.save(update_fields=fields)
    return appointment
