from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from apps.accounts.permissions import VendorRequiredMixin
from apps.core.models import SiteSettings

from ..forms import SiteSettingsForm


class SiteSettingsView(VendorRequiredMixin, UpdateView):
    form_class = SiteSettingsForm
    template_name = "dashboard/settings.html"
    success_url = reverse_lazy("dashboard:settings")
    extra_context = {"nav": "settings"}

    def get_object(self, queryset=None):
        return SiteSettings.load()

    def form_valid(self, form):
        messages.success(self.request, "Settings saved.")
        return super().form_valid(form)
