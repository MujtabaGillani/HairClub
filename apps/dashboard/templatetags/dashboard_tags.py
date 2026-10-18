from django import template

from apps.appointments.models import Appointment, AppointmentStatus
from apps.orders.models import Order, OrderStatus

register = template.Library()


@register.simple_tag
def dashboard_badges() -> dict:
    """Counts shown next to sidebar links so vendors see what needs attention."""
    return {
        "appointments": Appointment.objects.filter(status=AppointmentStatus.PENDING).count(),
        "orders": Order.objects.filter(status=OrderStatus.PENDING).count(),
    }


@register.inclusion_tag("dashboard/partials/sort_th.html", takes_context=True)
def sort_th(context, label, asc_key, desc_key, css_class=""):
    """
    A clickable table header. Clicking toggles between ``asc_key`` and
    ``desc_key`` (both must be keys of the view's sort_options).
    """
    request = context["request"]
    current = context.get("sort", "")
    if asc_key == desc_key:  # single-direction column (e.g. alphabetical)
        target, direction = asc_key, ("asc" if current == asc_key else "")
    elif current == desc_key:
        target, direction = asc_key, "desc"
    elif current == asc_key:
        target, direction = desc_key, "asc"
    else:
        target, direction = desc_key, ""
    params = request.GET.copy()
    params["sort"] = target
    params.pop("page", None)
    aria = {"asc": "ascending", "desc": "descending"}.get(direction, "none")
    return {
        "label": label,
        "href": f"?{params.urlencode()}",
        "direction": direction,
        "aria": aria,
        "css_class": css_class,
    }
