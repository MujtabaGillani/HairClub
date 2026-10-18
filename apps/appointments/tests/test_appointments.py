from datetime import time, timedelta
from decimal import Decimal
from urllib.parse import unquote

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus
from apps.appointments.services import InvalidTransition, change_appointment_status, get_slots
from apps.core.models import SiteSettings
from apps.core.testing import make_service, make_user


class BookingTestCase(TestCase):
    def setUp(self):
        self.site = SiteSettings.load()
        self.site.opening_time = time(10, 0)
        self.site.closing_time = time(12, 0)
        self.site.slot_interval_minutes = 30
        self.site.slot_capacity = 1
        self.site.closed_weekdays = ""
        self.site.whatsapp_number = "923001112233"
        self.site.save()
        self.service = make_service(name="Hair Patch Fitting")
        self.day = timezone.localdate() + timedelta(days=3)

    def book(self, **overrides):
        data = {
            "full_name": "Sara Ahmed",
            "phone": "0321 7654321",
            "email": "sara@example.com",
            "service": self.service.pk,
            "date": self.day.isoformat(),
            "time": "10:30",
            "notes": "First visit",
        }
        data.update(overrides)
        return self.client.post(reverse("appointments:book"), data)


class SlotTests(BookingTestCase):
    def test_slots_follow_opening_hours(self):
        self.assertEqual([s.value for s in get_slots(self.day)], ["10:00", "10:30", "11:00", "11:30"])

    def test_closed_day_has_no_slots(self):
        self.site.closed_weekdays = str(self.day.weekday())
        self.site.save()
        self.assertEqual(get_slots(self.day), [])

    def test_past_and_far_future_dates_have_no_slots(self):
        self.assertEqual(get_slots(timezone.localdate() - timedelta(days=1)), [])
        self.assertEqual(get_slots(timezone.localdate() + timedelta(days=365)), [])

    def test_booked_slot_has_no_remaining_capacity(self):
        Appointment.objects.create(full_name="X", phone="0300", service=self.service, date=self.day, time=time(10, 30))
        slots = {s.value: s.available for s in get_slots(self.day)}
        self.assertFalse(slots["10:30"])
        self.assertTrue(slots["11:00"])

    def test_cancelled_appointments_free_the_slot(self):
        Appointment.objects.create(
            full_name="X",
            phone="0300",
            service=self.service,
            date=self.day,
            time=time(10, 30),
            status=AppointmentStatus.CANCELLED,
        )
        self.assertTrue({s.value: s.available for s in get_slots(self.day)}["10:30"])

    def test_slots_endpoint(self):
        response = self.client.get(reverse("appointments:slots"), {"date": self.day.isoformat()})
        self.assertEqual(len(response.json()["slots"]), 4)
        self.assertEqual(self.client.get(reverse("appointments:slots"), {"date": "bad"}).status_code, 400)


class BookingFlowTests(BookingTestCase):
    def test_booking_saves_request_and_builds_whatsapp_message(self):
        response = self.book()
        appointment = Appointment.objects.get()
        self.assertRedirects(response, reverse("appointments:booked", args=[appointment.reference]))
        self.assertEqual(appointment.status, AppointmentStatus.PENDING)
        self.assertEqual(appointment.time, time(10, 30))

        page = self.client.get(response["Location"])
        url = page.context["whatsapp_url"]
        self.assertTrue(url.startswith("https://wa.me/923001112233?text="))
        message = unquote(url.split("text=", 1)[1])
        for expected in (
            "Sara Ahmed",
            "0321 7654321",
            "Hair Patch Fitting",
            "10:30 AM",
            "First visit",
            appointment.reference,
        ):
            self.assertIn(expected, message)

    def test_booking_by_signed_in_user_is_linked(self):
        user = make_user()
        self.client.force_login(user)
        self.book()
        self.assertEqual(Appointment.objects.get().user, user)

    def test_full_slot_is_rejected(self):
        self.book()
        self.client.cookies.clear()
        response = self.book(full_name="Someone Else")
        self.assertEqual(response.status_code, 200)
        self.assertIn("time", response.context["form"].errors)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_past_date_rejected(self):
        response = self.book(date=(timezone.localdate() - timedelta(days=1)).isoformat())
        self.assertIn("date", response.context["form"].errors)

    def test_closed_day_rejected(self):
        self.site.closed_weekdays = str(self.day.weekday())
        self.site.save()
        response = self.book()
        self.assertIn("date", response.context["form"].errors)

    def test_invalid_phone_rejected(self):
        response = self.book(phone="12")
        self.assertIn("phone", response.context["form"].errors)

    def test_inactive_service_cannot_be_booked(self):
        self.service.is_active = False
        self.service.save()
        response = self.book()
        self.assertIn("service", response.context["form"].errors)

    def test_booked_page_is_private_to_the_session(self):
        self.book()
        appointment = Appointment.objects.get()
        self.client.cookies.clear()
        self.assertEqual(self.client.get(reverse("appointments:booked", args=[appointment.reference])).status_code, 404)


class StatusTransitionTests(BookingTestCase):
    def test_workflow(self):
        appt = Appointment.objects.create(
            full_name="X", phone="0300", service=self.service, date=self.day, time=time(10)
        )
        appt = change_appointment_status(appt, AppointmentStatus.CONFIRMED, note="Called client")
        self.assertIn("Called client", appt.vendor_note)
        appt = change_appointment_status(appt, AppointmentStatus.COMPLETED, amount_charged=Decimal("5000"))
        with self.assertRaises(InvalidTransition):
            change_appointment_status(appt, AppointmentStatus.PENDING)
