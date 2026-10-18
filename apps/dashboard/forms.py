from datetime import date
from decimal import Decimal

from django import forms
from django.conf import settings

from apps.appointments.models import AppointmentStatus, Service
from apps.catalog.models import Category, Product, ProductImage
from apps.catalog.validators import validate_product_image
from apps.core.models import SiteSettings, Weekday
from apps.finance.models import Expense, ExpenseCategory
from apps.finance.services import PERIOD_CHOICES
from apps.inventory.models import MovementReason
from apps.orders.models import OrderStatus, PaymentMethod, PaymentStatus


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleImageInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        cleaned = []
        for f in files:
            single = super().clean(f, initial)
            validate_product_image(single)
            cleaned.append(single)
        return cleaned


class ProductForm(forms.ModelForm):
    """
    Product create / edit. Images are handled here too so the min/max image
    rule is validated together with the rest of the product.
    Stock is only set on creation; later changes go through Inventory so they
    are recorded in the stock ledger.
    """

    initial_stock = forms.IntegerField(min_value=0, initial=0, label="Opening stock")
    new_images = MultipleImageField(
        required=False,
        label="Upload images",
        help_text=f"JPEG, PNG or WebP, up to {settings.PRODUCT_IMAGE_MAX_BYTES // (1024 * 1024)} MB each.",
    )
    remove_images = forms.ModelMultipleChoiceField(queryset=None, required=False, widget=forms.CheckboxSelectMultiple)
    primary_image = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Product
        fields = [
            "name",
            "category",
            "brand",
            "sku",
            "short_description",
            "description",
            "specifications",
            "price",
            "discount_percent",
            "show_price",
            "purchase_cost",
            "inbound_shipping_cost",
            "other_cost",
            "low_stock_threshold",
            "is_active",
            "is_featured",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "specifications": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": 'Base: Fine mono lace\nHair type: 100% Remy human hair\nSize: 8" × 10"',
                }
            ),
            "price": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "discount_percent": forms.NumberInput(attrs={"min": 0, "max": 90}),
            "purchase_cost": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "inbound_shipping_cost": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "other_cost": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }
        labels = {"sku": "SKU (optional)", "discount_percent": "Discount %", "is_active": "Published"}
        help_texts = {
            "sku": "Leave blank to auto-generate.",
            "show_price": "Untick to show “Price on request”.",
            "discount_percent": "0–90",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.all()
        is_new = self.instance.pk is None
        self.existing_images = list(self.instance.images.all()) if not is_new else []
        self.fields["remove_images"].queryset = self.instance.images.all() if not is_new else Product.objects.none()
        if not is_new:
            del self.fields["initial_stock"]
        for name in self.COST_FIELDS:  # optional: blank means "not known yet" and is stored as 0
            self.fields[name].required = False

    COST_FIELDS = ("purchase_cost", "inbound_shipping_cost", "other_cost")

    def _clean_cost(self, name):
        value = self.cleaned_data.get(name)
        return value if value is not None else Decimal("0.00")

    def clean_purchase_cost(self):
        return self._clean_cost("purchase_cost")

    def clean_inbound_shipping_cost(self):
        return self._clean_cost("inbound_shipping_cost")

    def clean_other_cost(self):
        return self._clean_cost("other_cost")

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip().upper()
        if sku and Product.objects.filter(sku__iexact=sku).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another product already uses this SKU.")
        return sku

    def clean(self):
        cleaned = super().clean()
        removing = {img.pk for img in cleaned.get("remove_images") or []}
        kept = [img for img in self.existing_images if img.pk not in removing]
        new = cleaned.get("new_images") or []
        total = len(kept) + len(new)
        lo, hi = settings.PRODUCT_MIN_IMAGES, settings.PRODUCT_MAX_IMAGES
        if total < lo:
            self.add_error("new_images", f"Add at least {lo} image{'s' if lo > 1 else ''}.")
        elif total > hi:
            self.add_error(
                "new_images",
                f"A product can have at most {hi} images (you would have {total}). Remove some first.",
            )
        self.kept_images = kept
        return cleaned

    def save_images(self, product: Product) -> None:
        """Apply image removals / uploads and make sure exactly one image is primary."""
        for image in self.cleaned_data.get("remove_images") or []:
            image.delete()

        next_order = max((img.sort_order for img in self.kept_images), default=-1) + 1
        created = [
            ProductImage.objects.create(product=product, image=upload, alt_text=product.name, sort_order=next_order + i)
            for i, upload in enumerate(self.cleaned_data.get("new_images") or [])
        ]

        choice = self.cleaned_data.get("primary_image") or ""
        target = None
        if choice.startswith("existing-"):
            target = next((img for img in self.kept_images if str(img.pk) == choice.removeprefix("existing-")), None)
        elif choice.startswith("new-") and choice.removeprefix("new-").isdigit():
            index = int(choice.removeprefix("new-"))
            target = created[index] if index < len(created) else None
        if target is None:
            target = next((img for img in self.kept_images if img.is_primary), None)
        if target is None:
            target = (self.kept_images + created)[0] if (self.kept_images or created) else None
        if target is not None:
            product.images.exclude(pk=target.pk).update(is_primary=False)
            ProductImage.objects.filter(pk=target.pk).update(is_primary=True)


class StockAdjustmentForm(forms.Form):
    MODE_ADD, MODE_REMOVE, MODE_SET = "add", "remove", "set"
    MODE_CHOICES = [(MODE_ADD, "Add stock"), (MODE_REMOVE, "Remove stock"), (MODE_SET, "Set exact count")]
    REASON_CHOICES = [
        (MovementReason.RESTOCK, MovementReason.RESTOCK.label),
        (MovementReason.RETURN, MovementReason.RETURN.label),
        (MovementReason.DAMAGED, MovementReason.DAMAGED.label),
        (MovementReason.CORRECTION, MovementReason.CORRECTION.label),
    ]

    mode = forms.ChoiceField(choices=MODE_CHOICES, initial=MODE_ADD)
    quantity = forms.IntegerField(min_value=0, max_value=100000)
    reason = forms.ChoiceField(choices=REASON_CHOICES)
    note = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, product=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.product = product

    def clean(self):
        cleaned = super().clean()
        mode, qty = cleaned.get("mode"), cleaned.get("quantity")
        if mode is None or qty is None or self.product is None:
            return cleaned
        if mode == self.MODE_ADD:
            delta = qty
        elif mode == self.MODE_REMOVE:
            delta = -qty
            if qty > self.product.stock:
                self.add_error("quantity", f"Only {self.product.stock} in stock.")
        else:
            delta = qty - self.product.stock
        if delta == 0:
            self.add_error("quantity", "This would not change the stock level.")
        cleaned["delta"] = delta
        return cleaned


class StatusChangeForm(forms.Form):
    status = forms.ChoiceField(choices=[])
    note = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, allowed: list[tuple[str, str]], **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = allowed


class AppointmentStatusForm(StatusChangeForm):
    amount_charged = forms.DecimalField(
        label="Amount charged",
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        help_text="Required when completing: what the client paid (0 if free).",
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == AppointmentStatus.COMPLETED and cleaned.get("amount_charged") is None:
            self.add_error("amount_charged", "Enter the amount charged (0 if it was free).")
        return cleaned


class OrderStatusForm(StatusChangeForm):
    tracking_number = forms.CharField(max_length=60, required=False)


class AppointmentFilterForm(forms.Form):
    q = forms.CharField(required=False)
    status = forms.ChoiceField(choices=[("", "All statuses")] + AppointmentStatus.choices, required=False)
    date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))


class OrderFilterForm(forms.Form):
    q = forms.CharField(required=False)
    status = forms.ChoiceField(choices=[("", "All statuses")] + OrderStatus.choices, required=False)
    payment_status = forms.ChoiceField(choices=[("", "Any payment")] + PaymentStatus.choices, required=False)
    payment_method = forms.ChoiceField(choices=[("", "Any method")] + PaymentMethod.choices, required=False)


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = [
            "name",
            "short_description",
            "description",
            "duration_minutes",
            "starting_price",
            "icon",
            "sort_order",
            "is_active",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class SiteSettingsForm(forms.ModelForm):
    closed_days = forms.TypedMultipleChoiceField(
        choices=Weekday.choices,
        coerce=int,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Closed on",
    )

    class Meta:
        model = SiteSettings
        fields = [
            "business_name",
            "tagline",
            "whatsapp_number",
            "phone",
            "email",
            "address",
            "instagram_url",
            "facebook_url",
            "tiktok_url",
            "opening_time",
            "closing_time",
            "slot_interval_minutes",
            "slot_capacity",
            "min_booking_notice_hours",
            "standard_shipping_fee",
            "express_shipping_fee",
            "free_shipping_threshold",
            "bank_transfer_instructions",
        ]
        widgets = {
            "opening_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "closing_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "bank_transfer_instructions": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["closed_days"].initial = self.instance.closed_weekday_list

    def clean(self):
        cleaned = super().clean()
        opening, closing = cleaned.get("opening_time"), cleaned.get("closing_time")
        if opening and closing and opening >= closing:
            self.add_error("closing_time", "Closing time must be after opening time.")
        return cleaned

    def save(self, commit=True):
        self.instance.closed_weekdays = ",".join(str(d) for d in sorted(self.cleaned_data.get("closed_days") or []))
        return super().save(commit)


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "category", "amount", "description", "paid_to", "payment_method", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "description": forms.TextInput(attrs={"placeholder": "e.g. October salary, shop rent, staff lunch"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = ExpenseCategory.objects.active()
        if self.instance.pk:  # keep the current category selectable even if it was deactivated
            qs = ExpenseCategory.objects.filter(pk=self.instance.category_id) | qs
        self.fields["category"].queryset = qs.distinct()
        self.fields["category"].empty_label = "Select a category"


class ExpenseFilterForm(forms.Form):
    month = forms.CharField(required=False, widget=forms.TextInput(attrs={"type": "month"}))
    category = forms.ModelChoiceField(
        queryset=ExpenseCategory.objects.all(), required=False, empty_label="All categories"
    )
    q = forms.CharField(required=False)

    def clean_month(self):
        value = self.cleaned_data.get("month") or ""
        if not value:
            return None
        try:
            year, month = (int(p) for p in value.split("-"))
            return date(year, month, 1)
        except ValueError as exc:
            raise forms.ValidationError("Choose a valid month.") from exc


class FinancePeriodForm(forms.Form):
    period = forms.ChoiceField(choices=list(PERIOD_CHOICES.items()), required=False)
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
