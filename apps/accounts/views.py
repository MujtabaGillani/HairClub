from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, TemplateView, UpdateView

from apps.appointments.models import Appointment
from apps.orders.models import Order

from .forms import ProfileForm


@login_required
def login_redirect(request):
    """Send vendors to their dashboard and customers to their account."""
    if request.user.is_vendor:
        return redirect("dashboard:overview")
    return redirect("accounts:overview")


class AccountOverviewView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        orders = Order.objects.filter(user=user)
        upcoming = Appointment.objects.for_user(user).upcoming().select_related("service")
        context["order_count"] = orders.count()
        context["recent_orders"] = orders[:5]
        context["upcoming_count"] = upcoming.count()
        context["upcoming_appointments"] = upcoming[:5]
        context["wishlist_count"] = user.wishlist_items.count()
        context["active_tab"] = "overview"
        return context


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile_form.html"
    success_url = reverse_lazy("accounts:profile")
    extra_context = {"active_tab": "profile"}

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Your profile has been updated.")
        return super().form_valid(form)


class MyOrdersView(LoginRequiredMixin, ListView):
    template_name = "accounts/orders.html"
    context_object_name = "orders"
    paginate_by = 10
    extra_context = {"active_tab": "orders"}

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items")


class MyAppointmentsView(LoginRequiredMixin, ListView):
    template_name = "accounts/appointments.html"
    context_object_name = "appointments"
    paginate_by = 10
    extra_context = {"active_tab": "appointments"}

    def get_queryset(self):
        return Appointment.objects.for_user(self.request.user).select_related("service")
