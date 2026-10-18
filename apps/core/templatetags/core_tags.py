from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


@register.filter
def money(value):
    """Render a price with the configured currency symbol, e.g. ``Rs. 12,500``."""
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    formatted = intcomma(f"{amount:.2f}")
    if formatted.endswith(".00"):
        formatted = formatted[:-3]
    return f"{settings.CURRENCY_SYMBOL} {formatted}"


@register.simple_tag(takes_context=True)
def active_nav(context, *url_prefixes, css_class="active"):
    """Return ``css_class`` when the current path starts with one of the prefixes."""
    request = context.get("request")
    if request is None:
        return ""
    path = request.path
    for prefix in url_prefixes:
        if prefix == "/" and path == "/":
            return css_class
        if prefix != "/" and path.startswith(prefix):
            return css_class
    return ""


@register.filter
def status_badge(status):
    """Map an order / appointment status to a Bootstrap colour."""
    return {
        "pending": "warning",
        "confirmed": "info",
        "processing": "primary",
        "shipped": "primary",
        "delivered": "success",
        "completed": "success",
        "cancelled": "secondary",
        "no_show": "danger",
        "paid": "success",
        "unpaid": "warning",
        "refunded": "secondary",
    }.get(str(status), "secondary")


_CHECK_WIDGETS = {"checkbox", "radio"}
_SELECT_WIDGETS = {"select", "selectmultiple", "nullbooleanselect"}


@register.filter
def bs_widget(bound_field, extra_classes=""):
    """Render a form widget with the right Bootstrap classes (and ``is-invalid`` on error)."""
    widget_type = bound_field.widget_type
    if widget_type in _CHECK_WIDGETS:
        css = "form-check-input"
    elif widget_type in _SELECT_WIDGETS:
        css = "form-select"
    else:
        css = "form-control"
    existing = bound_field.field.widget.attrs.get("class", "")
    classes = " ".join(c for c in (css, existing, extra_classes, "is-invalid" if bound_field.errors else "") if c)
    attrs = {"class": classes}
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
    if bound_field.help_text:
        attrs["aria-describedby"] = f"{bound_field.auto_id}_help"
    return bound_field.as_widget(attrs=attrs)
