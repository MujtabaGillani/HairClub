from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import Invoice, InvoicePaymentMethod


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "number",
            "invoice_date",
            "due_date",
            "delivery_date",
            "reference",
            "customer_name",
            "phone",
            "email",
            "billing_address",
            "shipping_address",
            "payment_method",
            "discount_amount",
            "delivery_charge",
            "tax_percent",
            "amount_paid",
            "paid_on",
            "notes",
            "payment_terms",
        ]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "delivery_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "paid_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "billing_address": forms.Textarea(attrs={"rows": 2}),
            "shipping_address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "payment_terms": forms.Textarea(attrs={"rows": 2}),
            "reference": forms.TextInput(attrs={"placeholder": "Order # or appointment ref"}),
            "discount_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "delivery_charge": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "tax_percent": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100"}),
            "amount_paid": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }
        labels = {
            "number": "Invoice number",
            "discount_amount": "Discount amount",
            "delivery_charge": "Delivery charge",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].required = False
        self.fields["payment_method"].choices = InvoicePaymentMethod.choices
        for name in ("discount_amount", "delivery_charge", "tax_percent", "amount_paid"):
            self.fields[name].required = False
        self.fields["paid_on"].help_text = "Defaults to today when an amount is paid."

    def clean_number(self):
        number = self.cleaned_data["number"].strip().upper()
        if Invoice.objects.filter(number__iexact=number).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This invoice number is already used.")
        return number

    def clean(self):
        cleaned = super().clean()
        for name in ("discount_amount", "delivery_charge", "tax_percent", "amount_paid"):
            if cleaned.get(name) is None:
                cleaned[name] = Decimal("0")
        issued, due = cleaned.get("invoice_date"), cleaned.get("due_date")
        if issued and due and due < issued:
            self.add_error("due_date", "The due date can't be before the invoice date.")
        paid_on = cleaned.get("paid_on")
        if paid_on and paid_on > timezone.localdate():
            self.add_error("paid_on", "The payment date can't be in the future.")
        return cleaned


class InvoiceItemForm(forms.Form):
    quantity = forms.DecimalField(min_value=Decimal("0.01"), max_digits=10, decimal_places=2, initial=1)
    description = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Search products & services, or type your own",
                "autocomplete": "off",
                "role": "combobox",
                "aria-autocomplete": "list",
                "aria-expanded": "false",
                "data-item-lookup": "",
            }
        ),
    )
    unit_price = forms.DecimalField(min_value=Decimal("0"), max_digits=12, decimal_places=2)


InvoiceItemFormSet = forms.formset_factory(
    InvoiceItemForm, extra=0, min_num=1, validate_min=True, max_num=50, validate_max=True, can_delete=True
)


def item_rows(formset) -> list[dict]:
    """Valid, non-deleted item rows in display order."""
    return [form.cleaned_data for form in formset.forms if form.cleaned_data and not form.cleaned_data.get("DELETE")]


class PaymentForm(forms.Form):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    paid_on = forms.DateField(
        initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    method = forms.ChoiceField(choices=InvoicePaymentMethod.choices, required=False)

    def clean_paid_on(self):
        value = self.cleaned_data["paid_on"]
        if value > timezone.localdate():
            raise forms.ValidationError("The payment date can't be in the future.")
        return value


class SendInvoiceEmailForm(forms.Form):
    to = forms.EmailField(label="Send to")
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}))
