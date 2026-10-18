from datetime import datetime

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET
from django.views.generic import ListView

from apps.core.models import SiteSettings

from .forms import AppointmentForm
from .models import Appointment, Service
from .services import SlotUnavailable, create_appointment, get_slots, vendor_whatsapp_url

BOOKED_SESSION_KEY = "booked_appointments"


class ServiceListView(ListView):
    template_name = "appointments/service_list.html"
    context_object_name = "services"

    def get_queryset(self):
        return Service.objects.active()


def book_appointment(request):
    initial = {}
    if slug := request.GET.get("service"):
        initial["service"] = Service.objects.active().filter(slug=slug).first()
    if request.user.is_authenticated:
        initial.update(full_name=request.user.get_full_name(), email=request.user.email, phone=request.user.phone)

    form = AppointmentForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            appointment = create_appointment(data=form.cleaned_data, user=request.user)
        except SlotUnavailable as exc:
            form.add_error("time", str(exc))
        else:
            booked = request.session.get(BOOKED_SESSION_KEY, [])
            request.session[BOOKED_SESSION_KEY] = (booked + [appointment.reference])[-20:]
            return redirect("appointments:booked", reference=appointment.reference)

    return render(request, "appointments/book.html", {"form": form, "services": Service.objects.active()})


def appointment_booked(request, reference):
    """Confirmation page that forwards the request to the salon's WhatsApp."""
    if reference not in request.session.get(BOOKED_SESSION_KEY, []):
        raise Http404("Appointment not found")
    appointment = get_object_or_404(Appointment.objects.select_related("service"), reference=reference)
    site = SiteSettings.load()
    return render(
        request,
        "appointments/booked.html",
        {"appointment": appointment, "whatsapp_url": vendor_whatsapp_url(appointment, site)},
    )


@require_GET
def available_slots(request):
    """JSON list of slots for the booking form's time picker."""
    try:
        day = datetime.strptime(request.GET.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"slots": [], "message": "Invalid date."}, status=400)

    slots = get_slots(day)
    if not slots:
        site = SiteSettings.load()
        closed = day.weekday() in site.closed_weekday_list
        message = f"We're closed on {day:%A}s." if closed else "No times available on this date."
        return JsonResponse({"slots": [], "message": message})
    return JsonResponse(
        {
            "slots": [{"value": s.value, "label": s.label, "available": s.available} for s in slots],
            "message": "" if any(s.available for s in slots) else "This day is fully booked.",
        }
    )
