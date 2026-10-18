"""Invoice domain logic: numbering, totals, PDF rendering and sending."""

import io
import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from apps.core.models import SiteSettings
from apps.core.whatsapp import build_whatsapp_url

from .models import Invoice, InvoiceItem, InvoiceStatus, money

logger = logging.getLogger(__name__)


class InvoiceError(Exception):
    """Raised for invoice actions that aren't allowed; the message is safe to show."""


def item_catalog() -> list[dict]:
    """
    Products and salon services offered as suggestions in the invoice item picker.
    Prices are the current selling prices (after any product discount).
    """
    from apps.appointments.models import Service
    from apps.catalog.models import Product

    products = [
        {
            "kind": "product",
            "name": p.name,
            "price": float(p.final_price),
            "meta": f"{p.sku} · {p.stock} in stock" if p.stock else f"{p.sku} · out of stock",
            "search": f"{p.name} {p.sku} {p.brand} {p.category.name}".lower(),
        }
        for p in Product.objects.filter(is_active=True).select_related("category").order_by("name")
    ]
    services = [
        {
            "kind": "service",
            "name": s.name,
            "price": float(s.starting_price or 0),
            "meta": f"{s.duration_minutes} min" + ("" if s.starting_price else " · price on consultation"),
            "search": s.name.lower(),
        }
        for s in Service.objects.active().order_by("sort_order", "name")
    ]
    return products + services


def default_initial(site: SiteSettings | None = None) -> dict:
    site = site or SiteSettings.load()
    return {
        "number": Invoice.next_number(),
        "invoice_date": timezone.localdate(),
        "notes": f"Thank you for choosing {site.business_name}.",
        "payment_terms": "Please pay by the due date.",
    }


def initial_from_order(order) -> tuple[dict, list[dict]]:
    header = {
        "order": order,
        "reference": order.number,
        "customer_name": order.full_name,
        "phone": order.phone,
        "email": order.email,
        "shipping_address": "" if order.is_pickup else order.shipping_address,
        "billing_address": "" if order.is_pickup else order.shipping_address,
        "delivery_charge": order.shipping_cost,
        "amount_paid": order.total if order.payment_status == "paid" else Decimal("0"),
        "payment_method": order.payment_method,
        "delivery_date": timezone.localtime(order.delivered_at).date() if order.delivered_at else None,
    }
    items = [
        {"description": item.product_name, "quantity": item.quantity, "unit_price": item.unit_price}
        for item in order.items.all()
    ]
    return header, items


def initial_from_appointment(appointment) -> tuple[dict, list[dict]]:
    price = appointment.amount_charged
    if price is None:
        price = appointment.service.starting_price or Decimal("0")
    header = {
        "appointment": appointment,
        "reference": appointment.reference,
        "customer_name": appointment.full_name,
        "phone": appointment.phone,
        "email": appointment.email,
        "delivery_date": appointment.date,
        "amount_paid": appointment.amount_charged or Decimal("0"),
    }
    items = [
        {"description": f"{appointment.service.name} ({appointment.date:%d %b %Y})", "quantity": 1, "unit_price": price}
    ]
    return header, items


@transaction.atomic
def save_invoice(invoice: Invoice, item_rows: list[dict], *, user=None) -> Invoice:
    """
    Persist the invoice and replace its items, recomputing all totals server-side
    (totals shown in the live preview are never trusted).
    """
    if invoice.pk is None and user is not None and user.is_authenticated:
        invoice.created_by = user
    if invoice.amount_paid and not invoice.paid_on:
        invoice.paid_on = timezone.localdate()
    if not invoice.amount_paid:
        invoice.paid_on = None

    items = [
        InvoiceItem(
            description=row["description"], quantity=row["quantity"], unit_price=row["unit_price"], sort_order=i
        )
        for i, row in enumerate(item_rows)
    ]
    invoice.recalculate(items)
    try:
        with transaction.atomic():
            invoice.save()
    except IntegrityError as exc:
        raise InvoiceError(f"Invoice number {invoice.number} is already used.") from exc
    invoice.items.all().delete()
    for item in items:
        item.invoice = invoice
    InvoiceItem.objects.bulk_create(items)
    return invoice


def record_payment(invoice: Invoice, amount: Decimal, *, paid_on=None, method: str = "") -> Invoice:
    if invoice.status == InvoiceStatus.VOID:
        raise InvoiceError("A void invoice can't take payments.")
    amount = money(amount)
    if amount <= 0:
        raise InvoiceError("Enter a payment amount above zero.")
    if amount > invoice.balance_due:
        raise InvoiceError(f"That's more than the balance due ({invoice.balance_due}).")
    invoice.amount_paid = money(invoice.amount_paid + amount)
    invoice.paid_on = paid_on or timezone.localdate()
    if method:
        invoice.payment_method = method
    if invoice.status == InvoiceStatus.DRAFT:
        invoice.status = InvoiceStatus.SENT
    invoice.recalculate()
    invoice.save()
    return invoice


def mark_sent(invoice: Invoice) -> Invoice:
    if invoice.status == InvoiceStatus.VOID:
        raise InvoiceError("A void invoice can't be sent.")
    invoice.status = InvoiceStatus.SENT
    invoice.sent_at = timezone.now()
    invoice.save(update_fields=["status", "sent_at", "updated_at"])
    return invoice


def void_invoice(invoice: Invoice) -> Invoice:
    invoice.status = InvoiceStatus.VOID
    invoice.save(update_fields=["status", "updated_at"])
    return invoice


# --- Rendering ---------------------------------------------------------------------


def document_context(invoice: Invoice) -> dict:
    return {
        "invoice": invoice,
        "items": list(invoice.items.all()),
        "site": SiteSettings.load(),
        "currency_symbol": settings.CURRENCY_SYMBOL,
    }


def render_pdf(invoice: Invoice) -> bytes:
    html = render_to_string("invoices/pdf.html", document_context(invoice))
    buffer = io.BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, encoding="utf-8")
    if result.err:
        raise InvoiceError("The PDF could not be generated.")
    return buffer.getvalue()


def pdf_filename(invoice: Invoice) -> str:
    return f"{invoice.number}.pdf"


# --- Sending -------------------------------------------------------------------------


def send_by_email(invoice: Invoice, *, to: str, subject: str, message: str, public_url: str) -> None:
    site = SiteSettings.load()
    body = f"{message.strip()}\n\nView online: {public_url}\n\n{site.business_name}\n{site.phone}"
    email = EmailMessage(
        subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[to], reply_to=[site.email]
    )
    email.attach(pdf_filename(invoice), render_pdf(invoice), "application/pdf")
    email.send(fail_silently=False)
    mark_sent(invoice)


def whatsapp_message(invoice: Invoice, public_url: str) -> str:
    site = SiteSettings.load()
    symbol = settings.CURRENCY_SYMBOL
    lines = [
        f"Hi {invoice.customer_name}, here is your invoice {invoice.number} from {site.business_name}.",
        "",
        f"Total: {symbol} {invoice.total:,.0f}",
    ]
    if invoice.amount_paid:
        lines.append(f"Paid: {symbol} {invoice.amount_paid:,.0f}")
    if invoice.balance_due > 0:
        lines.append(f"Balance due: {symbol} {invoice.balance_due:,.0f}")
        if invoice.due_date:
            lines.append(f"Due by: {invoice.due_date:%d %b %Y}")
    lines += ["", f"View / download (PDF): {public_url}", "", "Thank you!"]
    return "\n".join(lines)


def whatsapp_url(invoice: Invoice, public_url: str) -> str:
    return build_whatsapp_url(invoice.phone, whatsapp_message(invoice, public_url))
