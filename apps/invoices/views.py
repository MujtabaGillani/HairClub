"""Public, token-protected invoice pages for customers (no login needed)."""

from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.dashboard.views.invoices import pdf_response

from .models import Invoice, InvoiceStatus
from .services import document_context


def _get(token):
    return get_object_or_404(Invoice.objects.exclude(status=InvoiceStatus.DRAFT), public_token=token)


@require_GET
def public_invoice(request, token):
    invoice = _get(token)
    response = render(request, "invoices/public.html", document_context(invoice))
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


@require_GET
def public_invoice_pdf(request, token):
    response = pdf_response(_get(token), download=request.GET.get("download") == "1")
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
