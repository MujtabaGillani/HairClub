from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.permissions import VendorRequiredMixin
from apps.core.whatsapp import build_whatsapp_url
from apps.orders.models import Order, OrderStatus
from apps.orders.services import InvalidTransition, change_order_status, mark_order_paid

from ..forms import OrderFilterForm, OrderStatusForm


class OrderListView(VendorRequiredMixin, ListView):
    template_name = "dashboard/orders/list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        self.filter_form = OrderFilterForm(self.request.GET or None)
        qs = Order.objects.annotate(units=Sum("items__quantity")).order_by("-created_at")
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if term := (data.get("q") or "").strip():
                qs = qs.filter(
                    Q(number__icontains=term)
                    | Q(full_name__icontains=term)
                    | Q(email__icontains=term)
                    | Q(phone__icontains=term)
                )
            if data.get("status"):
                qs = qs.filter(status=data["status"])
        return qs

    def get_context_data(self, **kwargs):
        status_counts = dict(Order.objects.values_list("status").annotate(n=Count("id")).order_by())
        return super().get_context_data(
            nav="orders",
            filter_form=self.filter_form,
            status_counts=[(value, label, status_counts.get(value, 0)) for value, label in OrderStatus.choices],
            **kwargs,
        )


class OrderDetailView(VendorRequiredMixin, DetailView):
    template_name = "dashboard/orders/detail.html"
    context_object_name = "order"
    slug_field = "number"
    slug_url_kwarg = "number"

    def get_queryset(self):
        return Order.objects.prefetch_related("items__product__images", "events__created_by").select_related("user")

    def get_context_data(self, **kwargs):
        order = self.object
        message = f"Hi {order.full_name}, this is regarding your order {order.number}."
        return super().get_context_data(
            nav="orders",
            status_form=OrderStatusForm(
                allowed=order.allowed_transitions, initial={"tracking_number": order.tracking_number}
            ),
            customer_whatsapp_url=build_whatsapp_url(order.phone, message),
            **kwargs,
        )


class OrderStatusView(VendorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, number):
        order = get_object_or_404(Order, number=number)
        form = OrderStatusForm(request.POST, allowed=order.allowed_transitions)
        if not form.is_valid():
            messages.error(request, "Please choose a valid status.")
            return redirect("dashboard:order_detail", number=number)
        tracking = form.cleaned_data.get("tracking_number", "").strip()
        if tracking and tracking != order.tracking_number:
            order.tracking_number = tracking
            order.save(update_fields=["tracking_number", "updated_at"])
        try:
            order = change_order_status(
                order, form.cleaned_data["status"], user=request.user, note=form.cleaned_data["note"]
            )
        except InvalidTransition as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Order {order.number} is now {order.get_status_display().lower()}.")
        return redirect("dashboard:order_detail", number=number)


class OrderMarkPaidView(VendorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, number):
        order = get_object_or_404(Order, number=number)
        try:
            mark_order_paid(order, user=request.user)
        except InvalidTransition as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Order {order.number} marked as paid.")
        return redirect("dashboard:order_detail", number=number)
