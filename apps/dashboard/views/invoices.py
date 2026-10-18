from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.accounts.permissions import VendorRequiredMixin
from apps.appointments.models import Appointment
from apps.core.models import SiteSettings
from apps.invoices.forms import InvoiceForm, InvoiceItemFormSet, PaymentForm, SendInvoiceEmailForm, item_rows
from apps.invoices.models import Invoice, InvoiceStatus
from apps.invoices.services import (
    InvoiceError,
    default_initial,
    initial_from_appointment,
    initial_from_order,
    item_catalog,
    mark_sent,
    pdf_filename,
    record_payment,
    render_pdf,
    save_invoice,
    send_by_email,
    void_invoice,
    whatsapp_url,
)
from apps.orders.models import Order

from ..sorting import DATE_PRESETS, SortableListMixin, resolve_date_range

STATUS_FILTERS = {
    "draft": "Drafts",
    "unpaid": "Unpaid",
    "overdue": "Overdue",
    "partial": "Partly paid",
    "paid": "Paid",
    "void": "Void",
}


class InvoiceListView(VendorRequiredMixin, SortableListMixin, ListView):
    template_name = "dashboard/invoices/list.html"
    context_object_name = "invoices"
    paginate_by = 20
    sort_options = {
        "newest": ("Newest first", ["-invoice_date", "-number"]),
        "oldest": ("Oldest first", ["invoice_date", "number"]),
        "number": ("Invoice number", ["number"]),
        "customer": ("Customer A–Z", ["customer_name"]),
        "total_desc": ("Total: high to low", ["-total"]),
        "balance_desc": ("Balance due: high to low", ["-balance_due"]),
        "due": ("Due date", ["due_date"]),
    }
    default_sort = "newest"

    def get_queryset(self):
        params = self.request.GET
        qs = Invoice.objects.all()
        if term := params.get("q", "").strip():
            qs = qs.filter(
                Q(number__icontains=term)
                | Q(customer_name__icontains=term)
                | Q(phone__icontains=term)
                | Q(email__icontains=term)
                | Q(reference__icontains=term)
            )
        self.date_from, self.date_to, self.date_preset = resolve_date_range(params)
        if self.date_from:
            qs = qs.filter(invoice_date__gte=self.date_from)
        if self.date_to:
            qs = qs.filter(invoice_date__lte=self.date_to)
        status = params.get("status", "")
        if status == "draft":
            qs = qs.filter(status=InvoiceStatus.DRAFT)
        elif status == "void":
            qs = qs.filter(status=InvoiceStatus.VOID)
        elif status == "unpaid":
            qs = qs.outstanding()
        elif status == "overdue":
            qs = qs.overdue()
        elif status == "partial":
            qs = qs.active().filter(amount_paid__gt=0, balance_due__gt=0)
        elif status == "paid":
            qs = qs.active().filter(total__gt=0, balance_due__lte=0)
        return self.apply_sort(qs)

    def get_context_data(self, **kwargs):
        today = timezone.localdate()
        outstanding = Invoice.objects.outstanding().aggregate(value=Sum("balance_due"), count=Count("id"))
        paid_this_month = (
            Invoice.objects.active()
            .filter(paid_on__year=today.year, paid_on__month=today.month)
            .aggregate(value=Sum("amount_paid"))["value"]
        )
        return super().get_context_data(
            nav="invoices",
            status_filters=STATUS_FILTERS,
            current_status=self.request.GET.get("status", ""),
            outstanding_value=outstanding["value"] or 0,
            outstanding_count=outstanding["count"],
            overdue_count=Invoice.objects.overdue().count(),
            draft_count=Invoice.objects.filter(status=InvoiceStatus.DRAFT).count(),
            paid_this_month=paid_this_month or 0,
            date_from=self.date_from,
            date_to=self.date_to,
            date_preset=self.date_preset,
            date_presets=DATE_PRESETS,
            **kwargs,
        )


class InvoiceEditorView(VendorRequiredMixin, View):
    """Create (no pk) or edit an invoice: header form + line items, with a live preview."""

    template_name = "dashboard/invoices/form.html"

    def get_invoice(self):
        pk = self.kwargs.get("pk")
        if pk is None:
            return Invoice()
        invoice = get_object_or_404(Invoice, pk=pk)
        if not invoice.is_editable:
            raise InvoiceError("Void invoices can't be edited.")
        return invoice

    def initial_data(self, invoice):
        if invoice.pk:
            items = [
                {"description": i.description, "quantity": i.quantity, "unit_price": i.unit_price}
                for i in invoice.items.all()
            ]
            return {}, items
        header, items = default_initial(), [{"quantity": 1}]
        if number := self.request.GET.get("order"):
            order = Order.objects.filter(number=number).prefetch_related("items").first()
            if order:
                extra, items = initial_from_order(order)
                header.update(extra)
        elif ref := self.request.GET.get("appointment"):
            appointment = Appointment.objects.filter(reference=ref).select_related("service").first()
            if appointment:
                extra, items = initial_from_appointment(appointment)
                header.update(extra)
        return header, items

    def render_editor(self, request, invoice, form, formset):
        source = invoice.order or invoice.appointment or form.initial.get("order") or form.initial.get("appointment")
        return render(
            request,
            self.template_name,
            {
                "nav": "invoices",
                "invoice": invoice,
                # Unsaved invoices have no items yet; the live preview script fills them in.
                "preview_items": list(invoice.items.all()) if invoice.pk else [],
                "form": form,
                "formset": formset,
                "source": source,
                "site": SiteSettings.load(),
                "item_catalog": item_catalog(),
            },
        )

    def get(self, request, *args, **kwargs):
        try:
            invoice = self.get_invoice()
        except InvoiceError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:invoice_list")
        header, items = self.initial_data(invoice)
        form = InvoiceForm(instance=invoice, initial=header)
        formset = InvoiceItemFormSet(initial=items, prefix="items")
        return self.render_editor(request, invoice, form, formset)

    def post(self, request, *args, **kwargs):
        try:
            invoice = self.get_invoice()
        except InvoiceError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:invoice_list")
        form = InvoiceForm(request.POST, instance=invoice)
        formset = InvoiceItemFormSet(request.POST, prefix="items")
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            if invoice.pk is None:
                # Keep the link to the source document chosen when the editor was opened.
                if number := request.POST.get("source_order"):
                    invoice.order = Order.objects.filter(number=number).first()
                elif ref := request.POST.get("source_appointment"):
                    invoice.appointment = Appointment.objects.filter(reference=ref).first()
            rows = item_rows(formset)
            subtotal = sum((r["quantity"] * r["unit_price"] for r in rows), 0)
            if form.cleaned_data["discount_amount"] > subtotal:
                form.add_error("discount_amount", "The discount can't be more than the items subtotal.")
            else:
                try:
                    invoice = save_invoice(invoice, rows, user=request.user)
                except InvoiceError as exc:
                    form.add_error("number", str(exc))
                else:
                    if invoice.balance_due < 0:
                        messages.warning(request, "The amount paid is more than the total; the invoice shows a credit.")
                    messages.success(request, f"Invoice {invoice.number} saved.")
                    return redirect(invoice.get_absolute_url())
        return self.render_editor(request, invoice, form, formset)


class InvoiceDetailView(VendorRequiredMixin, View):
    def get(self, request, pk):
        invoice = get_object_or_404(Invoice.objects.select_related("order", "appointment"), pk=pk)
        public_url = request.build_absolute_uri(invoice.get_public_url())
        site = SiteSettings.load()
        email_form = SendInvoiceEmailForm(
            initial={
                "to": invoice.email,
                "subject": f"Invoice {invoice.number} from {site.business_name}",
                "message": f"Hi {invoice.customer_name},\n\nPlease find attached invoice {invoice.number}."
                + (f" The balance due is {invoice.balance_due:,.0f}." if invoice.balance_due > 0 else "")
                + "\n\nThank you!",
            }
        )
        return render(
            request,
            "dashboard/invoices/detail.html",
            {
                "nav": "invoices",
                "invoice": invoice,
                "items": list(invoice.items.all()),
                "site": site,
                "public_url": public_url,
                "email_form": email_form,
                "payment_form": PaymentForm(
                    initial={"amount": invoice.balance_due if invoice.balance_due > 0 else None}
                ),
            },
        )


class InvoicePdfView(VendorRequiredMixin, View):
    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        return pdf_response(invoice, download=request.GET.get("download") == "1")


def pdf_response(invoice, *, download: bool) -> HttpResponse:
    response = HttpResponse(render_pdf(invoice), content_type="application/pdf")
    disposition = "attachment" if download else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{pdf_filename(invoice)}"'
    return response


class InvoiceActionView(VendorRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk, action):
        invoice = get_object_or_404(Invoice, pk=pk)
        public_url = request.build_absolute_uri(invoice.get_public_url())
        try:
            if action == "send_email":
                form = SendInvoiceEmailForm(request.POST)
                if not form.is_valid():
                    raise InvoiceError("Enter a valid email address, subject and message.")
                if invoice.status == InvoiceStatus.VOID:
                    raise InvoiceError("A void invoice can't be sent.")
                send_by_email(invoice, public_url=public_url, **form.cleaned_data)
                if not invoice.email:
                    invoice.email = form.cleaned_data["to"]
                    invoice.save(update_fields=["email", "updated_at"])
                messages.success(request, f"Invoice {invoice.number} emailed to {form.cleaned_data['to']}.")
            elif action == "whatsapp":
                if not invoice.phone:
                    raise InvoiceError("Add the customer's phone number first.")
                mark_sent(invoice)
                return redirect(whatsapp_url(invoice, public_url))
            elif action == "mark_sent":
                mark_sent(invoice)
                messages.success(request, f"Invoice {invoice.number} marked as sent.")
            elif action == "payment":
                form = PaymentForm(request.POST)
                if not form.is_valid():
                    raise InvoiceError("Enter a valid amount and a date that isn't in the future.")
                record_payment(
                    invoice,
                    form.cleaned_data["amount"],
                    paid_on=form.cleaned_data["paid_on"],
                    method=form.cleaned_data["method"],
                )
                messages.success(request, f"Payment recorded. Balance due: {invoice.balance_due:,.2f}.")
            elif action == "void":
                void_invoice(invoice)
                messages.success(request, f"Invoice {invoice.number} voided.")
            elif action == "delete":
                if invoice.status != InvoiceStatus.DRAFT:
                    raise InvoiceError("Only drafts can be deleted. Void a sent invoice instead.")
                number = invoice.number
                invoice.delete()
                messages.success(request, f"Draft {number} deleted.")
                return redirect("dashboard:invoice_list")
            elif action == "duplicate":
                copy = Invoice.objects.get(pk=invoice.pk)
                items = [
                    {"description": i.description, "quantity": i.quantity, "unit_price": i.unit_price}
                    for i in invoice.items.all()
                ]
                copy.pk = None
                copy.number = Invoice.next_number()
                copy.status = InvoiceStatus.DRAFT
                copy.invoice_date = timezone.localdate()
                copy.amount_paid = 0
                copy.paid_on = None
                copy.sent_at = None
                copy.order = None
                copy.appointment = None
                copy.public_token = Invoice._meta.get_field("public_token").get_default()
                copy = save_invoice(copy, items, user=request.user)
                messages.success(request, f"Draft {copy.number} created from {invoice.number}.")
                return redirect(reverse("dashboard:invoice_update", args=[copy.pk]))
            else:
                raise InvoiceError("Unknown action.")
        except InvoiceError as exc:
            messages.error(request, str(exc))
        return redirect(invoice.get_absolute_url())
