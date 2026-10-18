from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.permissions import VendorRequiredMixin
from apps.appointments.models import BLOCKING_STATUSES, Appointment, AppointmentStatus
from apps.appointments.services import InvalidTransition, change_appointment_status, customer_whatsapp_url
from apps.core.http import redirect_next

from ..forms import AppointmentFilterForm, AppointmentStatusForm

VIEWS = {
    "upcoming": "Upcoming",
    "pending": "Awaiting confirmation",
    "today": "Today",
    "past": "Past",
    "all": "All",
}


class AppointmentListView(VendorRequiredMixin, ListView):
    template_name = "dashboard/appointments/list.html"
    context_object_name = "appointments"
    paginate_by = 20

    def get_queryset(self):
        self.view = self.request.GET.get("view") if self.request.GET.get("view") in VIEWS else "upcoming"
        self.filter_form = AppointmentFilterForm(self.request.GET or None)
        now = timezone.localtime()
        today = now.date()
        qs = Appointment.objects.select_related("service")

        if self.view == "upcoming":
            qs = qs.upcoming()
        elif self.view == "pending":
            qs = qs.filter(status=AppointmentStatus.PENDING).order_by("date", "time")
        elif self.view == "today":
            qs = qs.filter(date=today).order_by("time")
        elif self.view == "past":
            qs = qs.filter(Q(date__lt=today) | Q(date=today, time__lt=now.time())).order_by("-date", "-time")

        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("q"):
                term = data["q"].strip()
                qs = qs.filter(
                    Q(full_name__icontains=term)
                    | Q(phone__icontains=term)
                    | Q(reference__icontains=term)
                    | Q(email__icontains=term)
                )
            if data.get("status"):
                qs = qs.filter(status=data["status"])
            if data.get("date"):
                qs = qs.filter(date=data["date"])
        return qs

    def get_context_data(self, **kwargs):
        today = timezone.localdate()
        counts = Appointment.objects.aggregate(
            pending=Count("id", filter=Q(status=AppointmentStatus.PENDING)),
            today=Count("id", filter=Q(date=today, status__in=BLOCKING_STATUSES)),
            confirmed_upcoming=Count("id", filter=Q(date__gte=today, status=AppointmentStatus.CONFIRMED)),
        )
        return super().get_context_data(
            nav="appointments",
            views=VIEWS,
            current_view=self.view,
            filter_form=self.filter_form,
            counts=counts,
            **kwargs,
        )


class AppointmentDetailView(VendorRequiredMixin, DetailView):
    template_name = "dashboard/appointments/detail.html"
    context_object_name = "appointment"
    slug_field = "reference"
    slug_url_kwarg = "reference"

    def get_queryset(self):
        return Appointment.objects.select_related("service", "user", "handled_by")

    def get_context_data(self, **kwargs):
        appointment = self.object
        history = (
            Appointment.objects.filter(phone=appointment.phone).exclude(pk=appointment.pk).select_related("service")[:5]
        )
        return super().get_context_data(
            nav="appointments",
            status_form=AppointmentStatusForm(
                allowed=appointment.allowed_transitions,
                initial={"amount_charged": appointment.service.starting_price},
            ),
            customer_whatsapp_url=customer_whatsapp_url(appointment),
            notify_whatsapp_url=self.request.session.pop("notify_whatsapp", None),
            history=history,
            **kwargs,
        )


class AppointmentStatusView(VendorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, reference):
        appointment = get_object_or_404(Appointment, reference=reference)
        form = AppointmentStatusForm(request.POST, allowed=appointment.allowed_transitions)
        if not form.is_valid():
            errors = form.errors.get("amount_charged") or ["Please choose a valid status."]
            messages.error(request, errors[0])
            return redirect("dashboard:appointment_detail", reference=reference)
        try:
            appointment = change_appointment_status(
                appointment,
                form.cleaned_data["status"],
                user=request.user,
                note=form.cleaned_data["note"],
                amount_charged=form.cleaned_data.get("amount_charged"),
            )
        except InvalidTransition as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Appointment {appointment.reference} marked as {appointment.get_status_display().lower()}.",
            )
            if appointment.status in (AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED):
                request.session["notify_whatsapp"] = customer_whatsapp_url(appointment)
        return redirect_next(request, "dashboard:appointment_detail", reference=reference)
