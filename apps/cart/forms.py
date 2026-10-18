from django import forms
from django.conf import settings


class CartAddForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, max_value=settings.CART_MAX_QUANTITY_PER_ITEM, initial=1)


class CartUpdateForm(forms.Form):
    """Setting a quantity of 0 removes the line."""

    quantity = forms.IntegerField(min_value=0, max_value=settings.CART_MAX_QUANTITY_PER_ITEM)
