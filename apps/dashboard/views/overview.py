from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.permissions import VendorRequiredMixin
from apps.appointments.models import Appointment, AppointmentStatus
from apps.catalog.models import Product
from apps.orders.models import Order, OrderStatus


class OverviewView(VendorRequiredMixin, TemplateView):
    template_name = "dashboard/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        since = timezone.now() - timedelta(days=30)

        recent_sales = Order.objects.revenue().filter(created_at__gte=since)
        sales = recent_sales.aggregate(revenue=Sum("total"), count=Count("id"))
        appointment_counts = dict(
            Appointment.objects.filter(date__gte=today).values_list("status").annotate(n=Count("id")).order_by()
        )

        context.update(
            nav="overview",
            revenue_30d=sales["revenue"] or 0,
            orders_30d=sales["count"],
            pending_orders=Order.objects.filter(status=OrderStatus.PENDING).count(),
            pending_appointments=appointment_counts.get(AppointmentStatus.PENDING, 0),
            todays_appointments=Appointment.objects.blocking()
            .filter(date=today)
            .select_related("service")
            .order_by("time"),
            upcoming_appointments=Appointment.objects.upcoming().select_related("service")[:6],
            recent_orders=Order.objects.all()[:6],
            low_stock_products=Product.objects.low_stock().order_by("stock")[:6],
            out_of_stock_count=Product.objects.out_of_stock().count(),
            low_stock_count=Product.objects.low_stock().count(),
            product_count=Product.objects.count(),
        )
        return context
