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
from ..sorting import DATE_PRESETS, SortableListMixin, resolve_date_range


class OrderListView(VendorRequiredMixin, SortableListMixin, ListView):
    template_name = "dashboard/orders/list.html"
    context_object_name = "orders"
    paginate_by = 20
    sort_options = {
        "newest": ("Newest first", ["-created_at"]),
        "oldest": ("Oldest first", ["created_at"]),
        "total_desc": ("Total: high to low", ["-total"]),
        "total_asc": ("Total: low to high", ["total"]),
        "customer": ("Customer A–Z", ["full_name"]),
        "customer_desc": ("Customer Z–A", ["-full_name"]),
        "items_desc": ("Most items", ["-units"]),
        "items_asc": ("Fewest items", ["units"]),
        "status": ("Status", ["status"]),
        "status_desc": ("Status (reverse)", ["-status"]),
    }
    default_sort = "newest"

    def get_queryset(self):
        params = self.request.GET
        self.filter_form = OrderFilterForm(params or None)
        self.date_from, self.date_to, self.date_preset = resolve_date_range(params)

        # Everything except the status filter, so the status tabs show counts for the current search/dates.
        base = Order.objects.all()
        if self.date_from:
            base = base.filter(created_at__date__gte=self.date_from)
        if self.date_to:
            base = base.filter(created_at__date__lte=self.date_to)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if term := (data.get("q") or "").strip():
                base = base.filter(
                    Q(number__icontains=term)
                    | Q(full_name__icontains=term)
                    | Q(email__icontains=term)
                    | Q(phone__icontains=term)
                )
            if data.get("payment_status"):
                base = base.filter(payment_status=data["payment_status"])
            if data.get("payment_method"):
                base = base.filter(payment_method=data["payment_method"])
        self.base_qs = base

        qs = base
        if self.filter_form.is_valid() and self.filter_form.cleaned_data.get("status"):
            qs = qs.filter(status=self.filter_form.cleaned_data["status"])
        self.filtered_qs = qs
        return self.apply_sort(qs.annotate(units=Sum("items__quantity")))

    def get_context_data(self, **kwargs):
        status_counts = dict(self.base_qs.values_list("status").annotate(n=Count("id")).order_by())
        totals = self.filtered_qs.aggregate(value=Sum("total"), count=Count("id"))
        params = self.request.GET.copy()
        params.pop("status", None)
        params.pop("page", None)
        return super().get_context_data(
            nav="orders",
            filter_form=self.filter_form,
            status_counts=[(value, label, status_counts.get(value, 0)) for value, label in OrderStatus.choices],
            status_total=sum(status_counts.values()),
            tab_query=params.urlencode(),
            filtered_value=totals["value"] or 0,
            date_from=self.date_from,
            date_to=self.date_to,
            date_preset=self.date_preset,
            date_presets=DATE_PRESETS,
            has_filters=any(params.get(k) for k in ("q", "range", "from", "to", "payment_status", "payment_method"))
            or bool(self.request.GET.get("status")),
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
