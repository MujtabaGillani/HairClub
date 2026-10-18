from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import make_product, make_user, make_vendor
from apps.finance.services import build_report, resolve_period
from apps.invoices.models import Invoice, InvoiceStatus
from apps.invoices.services import record_payment, save_invoice
from apps.orders.models import Order, OrderItem

D = Decimal


def form_data(**overrides):
    data = {
        "number": "INV-0001",
        "invoice_date": timezone.localdate().isoformat(),
        "customer_name": "Bilal Ahmed",
        "phone": "03001234567",
        "email": "bilal@example.com",
        "payment_method": "",
        "discount_amount": "500",
        "delivery_charge": "250",
        "tax_percent": "10",
        "amount_paid": "0",
        "notes": "Thanks",
        "payment_terms": "Due in 7 days",
        "items-TOTAL_FORMS": "2",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "1",
        "items-MAX_NUM_FORMS": "50",
        "items-0-quantity": "1",
        "items-0-description": "Custom hair system",
        "items-0-unit_price": "40000",
        "items-1-quantity": "2",
        "items-1-description": "Adhesive",
        "items-1-unit_price": "2000",
    }
    data.update(overrides)
    return data


def make_invoice(**extra):
    invoice = Invoice(number=extra.pop("number", Invoice.next_number()), customer_name="Ali", **extra)
    return save_invoice(invoice, [{"description": "Hair system", "quantity": D("1"), "unit_price": D("10000")}])


class InvoiceModelTests(TestCase):
    def test_totals(self):
        invoice = Invoice(
            customer_name="A",
            discount_amount=D("500"),
            delivery_charge=D("250"),
            tax_percent=D("10"),
            amount_paid=D("1000"),
        )
        invoice = save_invoice(
            invoice,
            [
                {"description": "a", "quantity": D("1"), "unit_price": D("40000")},
                {"description": "b", "quantity": D("2"), "unit_price": D("2000")},
            ],
        )
        self.assertEqual(invoice.subtotal, D("44000.00"))
        self.assertEqual(invoice.tax_amount, D("4350.00"))  # 10% of (44000 - 500)
        self.assertEqual(invoice.total, D("48100.00"))  # 43500 + 4350 + 250
        self.assertEqual(invoice.balance_due, D("47100.00"))
        self.assertEqual(invoice.payment_state, "partial")
        self.assertEqual(invoice.paid_on, timezone.localdate())

    def test_numbering(self):
        self.assertEqual(Invoice.next_number(), "INV-0001")
        make_invoice(number="INV-0007")
        make_invoice(number="CUSTOM-1")
        self.assertEqual(Invoice.next_number(), "INV-0008")

    def test_payments_and_states(self):
        invoice = make_invoice()
        self.assertEqual(invoice.display_status[0], "Draft")
        record_payment(invoice, D("4000"))
        self.assertEqual((invoice.status, invoice.payment_state), (InvoiceStatus.SENT, "partial"))
        record_payment(invoice, D("6000"))
        self.assertEqual((invoice.payment_state, invoice.balance_due), ("paid", D("0.00")))

    def test_cannot_overpay(self):
        from apps.invoices.services import InvoiceError

        invoice = make_invoice()
        with self.assertRaises(InvoiceError):
            record_payment(invoice, D("10001"))


class InvoiceEditorTests(TestCase):
    def setUp(self):
        self.client.force_login(make_vendor())

    def test_create_invoice(self):
        response = self.client.post(reverse("dashboard:invoice_create"), form_data())
        invoice = Invoice.objects.get()
        self.assertRedirects(response, invoice.get_absolute_url())
        self.assertEqual(invoice.items.count(), 2)
        self.assertEqual(invoice.total, D("48100.00"))
        self.assertEqual(invoice.status, InvoiceStatus.DRAFT)

    def test_editor_prefills_number_and_renders_preview(self):
        response = self.client.get(reverse("dashboard:invoice_create"))
        self.assertContains(response, 'value="INV-0001"')
        self.assertContains(response, "data-invoice-doc")

    def test_validation(self):
        bad = form_data(**{"items-0-description": "", "number": ""})
        response = self.client.post(reverse("dashboard:invoice_create"), bad)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invoice.objects.exists())

        too_much_discount = form_data(discount_amount="999999")
        response = self.client.post(reverse("dashboard:invoice_create"), too_much_discount)
        self.assertIn("discount_amount", response.context["form"].errors)

        due_before = form_data(due_date="2000-01-01")
        response = self.client.post(reverse("dashboard:invoice_create"), due_before)
        self.assertIn("due_date", response.context["form"].errors)

    def test_duplicate_number_rejected(self):
        make_invoice(number="INV-0001")
        response = self.client.post(reverse("dashboard:invoice_create"), form_data())
        self.assertIn("number", response.context["form"].errors)

    def test_edit_replaces_items(self):
        invoice = make_invoice()
        data = form_data(number=invoice.number, **{"items-TOTAL_FORMS": "1"})
        self.client.post(reverse("dashboard:invoice_update", args=[invoice.pk]), data)
        invoice.refresh_from_db()
        self.assertEqual(list(invoice.items.values_list("description", flat=True)), ["Custom hair system"])

    def test_deleted_rows_are_ignored(self):
        data = form_data(**{"items-1-DELETE": "on"})
        self.client.post(reverse("dashboard:invoice_create"), data)
        self.assertEqual(Invoice.objects.get().items.count(), 1)

    def test_prefill_from_order_links_source(self):
        product = make_product(price=D("3000"))
        order = Order.objects.create(
            full_name="Sana", email="s@example.com", phone="0300", subtotal=6000, total=6250, shipping_cost=250
        )
        OrderItem.objects.create(
            order=order, product=product, product_name="Clay", sku="X", unit_price=3000, quantity=2, line_total=6000
        )
        response = self.client.get(reverse("dashboard:invoice_create"), {"order": order.number})
        self.assertContains(response, "Clay")
        self.assertContains(response, f'name="source_order" value="{order.number}"')
        data = form_data(customer_name="Sana", source_order=order.number, discount_amount="0", tax_percent="0")
        self.client.post(reverse("dashboard:invoice_create"), data)
        self.assertEqual(Invoice.objects.get().order, order)


class InvoiceSharingTests(TestCase):
    def setUp(self):
        self.client.force_login(make_vendor())
        self.invoice = make_invoice(phone="0300 1234567", email="ali@example.com")

    def action(self, name, **data):
        return self.client.post(reverse("dashboard:invoice_action", args=[self.invoice.pk, name]), data)

    def test_pdf_download(self):
        response = self.client.get(reverse("dashboard:invoice_pdf", args=[self.invoice.pk]), {"download": "1"})
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("attachment", response["Content-Disposition"])

    def test_email_attaches_pdf_and_marks_sent(self):
        self.action("send_email", to="ali@example.com", subject="Your invoice", message="Hello")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.attachments[0][0], f"{self.invoice.number}.pdf")
        self.assertIn(self.invoice.public_token, message.body)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.SENT)

    def test_whatsapp_redirects_with_public_link(self):
        response = self.action("whatsapp")
        self.assertTrue(response["Location"].startswith("https://wa.me/923001234567?text="))
        self.assertIn(self.invoice.public_token, response["Location"])

    def test_public_link_hidden_until_sent(self):
        self.client.logout()
        url = reverse("invoices:public", args=[self.invoice.public_token])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.invoice.status = InvoiceStatus.SENT
        self.invoice.save()
        self.assertContains(self.client.get(url), self.invoice.number)
        pdf = self.client.get(reverse("invoices:public_pdf", args=[self.invoice.public_token]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertEqual(self.client.get(reverse("invoices:public", args=["wrong-token"])).status_code, 404)

    def test_payment_void_delete_rules(self):
        self.action("payment", amount="10000", paid_on=timezone.localdate().isoformat(), method="cash")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.payment_state, "paid")
        self.action("delete")  # not a draft any more
        self.assertTrue(Invoice.objects.filter(pk=self.invoice.pk).exists())
        self.action("void")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.VOID)
        response = self.client.get(reverse("dashboard:invoice_update", args=[self.invoice.pk]))
        self.assertRedirects(response, reverse("dashboard:invoice_list"))

    def test_duplicate_creates_unpaid_draft(self):
        record_payment(self.invoice, D("10000"))
        self.action("duplicate")
        copy = Invoice.objects.exclude(pk=self.invoice.pk).get()
        self.assertEqual((copy.status, copy.amount_paid, copy.items.count()), (InvoiceStatus.DRAFT, D("0"), 1))
        self.assertNotEqual(copy.public_token, self.invoice.public_token)

    def test_access_control(self):
        self.client.force_login(make_user())
        for url in (
            reverse("dashboard:invoice_list"),
            reverse("dashboard:invoice_create"),
            reverse("dashboard:invoice_pdf", args=[self.invoice.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 403)


class InvoiceRevenueTests(TestCase):
    def test_only_paid_standalone_invoices_count(self):
        standalone = make_invoice()
        record_payment(standalone, D("4000"))
        order = Order.objects.create(full_name="A", email="a@example.com", phone="0300", subtotal=1, total=1)
        linked = make_invoice(order=order)
        record_payment(linked, D("10000"))
        voided = make_invoice()
        record_payment(voided, D("10000"))
        voided.status = InvoiceStatus.VOID
        voided.save()

        report = build_report(resolve_period("this_month"))
        self.assertEqual(report.invoice_revenue, D("4000"))
        self.assertEqual(report.invoices_paid, 1)
        self.assertEqual(report.revenue, D("4000"))


class ItemCatalogTests(TestCase):
    def test_editor_offers_products_and_services_with_prices(self):
        from apps.core.testing import make_service

        make_product(name="Lace System", price=D("40000"), discount_percent=10)
        make_product(name="Hidden Draft", is_active=False)
        make_service(name="Hair Patch Fitting", starting_price=D("8000"))
        self.client.force_login(make_vendor())
        response = self.client.get(reverse("dashboard:invoice_create"))
        catalog = {item["name"]: item for item in response.context["item_catalog"]}
        self.assertEqual(catalog["Lace System"]["price"], 36000.0)  # discounted selling price
        self.assertEqual(catalog["Hair Patch Fitting"]["kind"], "service")
        self.assertNotIn("Hidden Draft", catalog)
        self.assertContains(response, 'id="invoice-item-catalog"')
        self.assertContains(response, 'role="combobox"')
