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
