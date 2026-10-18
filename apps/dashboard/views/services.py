from django.contrib import messages
from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.permissions import VendorRequiredMixin
from apps.appointments.models import Service

from ..forms import ServiceForm


class ServiceListView(VendorRequiredMixin, ListView):
    template_name = "dashboard/services/list.html"
    context_object_name = "services"
    extra_context = {"nav": "services"}

    def get_queryset(self):
        return Service.objects.annotate(appointment_count=Count("appointments"))


class ServiceFormMixin(VendorRequiredMixin):
    model = Service
    form_class = ServiceForm
    template_name = "dashboard/services/form.html"
    success_url = reverse_lazy("dashboard:service_list")
    extra_context = {"nav": "services"}

    def form_valid(self, form):
        messages.success(self.request, f"Service “{form.instance.name}” saved.")
        return super().form_valid(form)


class ServiceCreateView(ServiceFormMixin, CreateView):
    pass


class ServiceUpdateView(ServiceFormMixin, UpdateView):
    pass
