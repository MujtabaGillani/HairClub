from django import forms

from .models import PaymentMethod, ShippingMethod


class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(
        help_text="We'll send your order confirmation here.",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    phone = forms.CharField(
        max_length=30,
        help_text="Our team may call or WhatsApp you to confirm delivery.",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "placeholder": "03XX XXXXXXX"}),
    )
    shipping_method = forms.ChoiceField(
        choices=ShippingMethod.choices, initial=ShippingMethod.STANDARD, widget=forms.RadioSelect
    )
    address_line1 = forms.CharField(
        label="Street address",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "address-line1"}),
    )
    address_line2 = forms.CharField(
        label="Apartment, suite, etc. (optional)",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "address-line2"}),
    )
    city = forms.CharField(
        max_length=100, required=False, widget=forms.TextInput(attrs={"autocomplete": "address-level2"})
    )
    province = forms.CharField(
        max_length=100, required=False, widget=forms.TextInput(attrs={"autocomplete": "address-level1"})
    )
    postal_code = forms.CharField(
        max_length=20, required=False, widget=forms.TextInput(attrs={"autocomplete": "postal-code"})
    )
    payment_method = forms.ChoiceField(
        choices=PaymentMethod.choices, initial=PaymentMethod.COD, widget=forms.RadioSelect
    )
    notes = forms.CharField(
        label="Order notes (optional)",
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Delivery instructions, preferred time, etc."}),
    )

    ADDRESS_FIELDS = ("address_line1", "city", "province")

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        digits = "".join(ch for ch in phone if ch.isdigit())
        if not 10 <= len(digits) <= 15:
            raise forms.ValidationError("Enter a valid phone number.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("shipping_method") != ShippingMethod.PICKUP:
            for field in self.ADDRESS_FIELDS:
                if not (cleaned.get(field) or "").strip():
                    self.add_error(field, "This field is required for delivery.")
        return cleaned


class OrderLookupForm(forms.Form):
    number = forms.CharField(
        label="Order number", max_length=20, widget=forms.TextInput(attrs={"placeholder": "HC261018-ABC123"})
    )
    email = forms.EmailField(label="Email used at checkout")

    def clean_number(self):
        return self.cleaned_data["number"].strip().upper()
