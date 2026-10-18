from datetime import datetime

from django import forms

from apps.core.models import SiteSettings

from .models import Service
from .services import booking_window, get_slots, is_open_on


class AppointmentForm(forms.Form):
    full_name = forms.CharField(
        label="Full name", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    phone = forms.CharField(
        label="WhatsApp / phone number",
        max_length=30,
        widget=forms.TextInput(attrs={"autocomplete": "tel", "placeholder": "03XX XXXXXXX"}),
    )
    email = forms.EmailField(
        label="Email (optional)", required=False, widget=forms.EmailInput(attrs={"autocomplete": "email"})
    )
    service = forms.ModelChoiceField(queryset=Service.objects.none(), empty_label="Select a service")
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    time = forms.ChoiceField(
        label="Preferred time",
        choices=[("", "Select a date first")],
        error_messages={"invalid_choice": "That time isn't available. Please pick another slot."},
    )
    notes = forms.CharField(
        label="Notes (optional)",
        required=False,
        max_length=1000,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Hair concerns, patch size, questions for our stylist…"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.site = SiteSettings.load()
        self.fields["service"].queryset = Service.objects.active()
        first, last = booking_window(self.site)
        self.fields["date"].widget.attrs.update(min=first.isoformat(), max=last.isoformat())

        day = self._selected_date()
        if day:
            slots = [s for s in get_slots(day, self.site) if s.available]
            if slots:
                self.fields["time"].choices = [("", "Select a time")] + [(s.value, s.label) for s in slots]
            else:
                self.fields["time"].choices = [("", "No times available on this date")]

    def _selected_date(self):
        raw = self.data.get(self.add_prefix("date")) if self.is_bound else self.initial.get("date")
        if not raw:
            return None
        if hasattr(raw, "year"):
            return raw
        try:
            return datetime.strptime(str(raw), "%Y-%m-%d").date()
        except ValueError:
            return None

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        digits = "".join(ch for ch in phone if ch.isdigit())
        if not 10 <= len(digits) <= 15:
            raise forms.ValidationError("Enter a valid phone number so we can reach you on WhatsApp.")
        return phone

    def clean_date(self):
        day = self.cleaned_data["date"]
        first, last = booking_window(self.site)
        if day < first:
            raise forms.ValidationError("Please choose today or a future date.")
        if day > last:
            raise forms.ValidationError(f"Bookings open up to {last:%d %B %Y}.")
        if not is_open_on(day, self.site):
            raise forms.ValidationError(f"We're closed on {day:%A}s. Please choose another day.")
        return day

    def clean_time(self):
        return datetime.strptime(self.cleaned_data["time"], "%H:%M").time()
