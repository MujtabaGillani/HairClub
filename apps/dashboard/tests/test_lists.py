from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.middleware import LAST_SEEN_KEY
from apps.core.testing import make_product, make_vendor
from apps.orders.models import Order, OrderStatus, PaymentStatus


def order(name, total, days_ago=0, **extra):
    o = Order.objects.create(full_name=name, email="x@example.com", phone="0300", subtotal=total, total=total, **extra)
    Order.objects.filter(pk=o.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    return o


class OrderListFilterSortTests(TestCase):
    def setUp(self):
        self.client.force_login(make_vendor())
        self.a = order("Ayesha", Decimal("500"), days_ago=0)
        self.b = order("Bilal", Decimal("9000"), days_ago=3, payment_status=PaymentStatus.PAID)
        self.c = order("Zara", Decimal("2000"), days_ago=40, status=OrderStatus.DELIVERED)
        self.url = reverse("dashboard:order_list")

    def names(self, **params):
        return [o.full_name for o in self.client.get(self.url, params).context["orders"]]

    def test_default_is_newest_first(self):
        self.assertEqual(self.names(), ["Ayesha", "Bilal", "Zara"])

    def test_sorting_options(self):
        self.assertEqual(self.names(sort="oldest"), ["Zara", "Bilal", "Ayesha"])
        self.assertEqual(self.names(sort="total_desc"), ["Bilal", "Zara", "Ayesha"])
        self.assertEqual(self.names(sort="customer_desc"), ["Zara", "Bilal", "Ayesha"])

    def test_unknown_sort_falls_back_safely(self):
        self.assertEqual(self.names(sort="password"), ["Ayesha", "Bilal", "Zara"])
        self.assertEqual(self.names(sort="-email"), ["Ayesha", "Bilal", "Zara"])

    def test_date_presets_and_custom_range(self):
        self.assertEqual(self.names(range="today"), ["Ayesha"])
        self.assertEqual(self.names(range="7d"), ["Ayesha", "Bilal"])
        today = timezone.localdate()
        start = (today - timedelta(days=45)).isoformat()
        end = (today - timedelta(days=2)).isoformat()
        self.assertEqual(self.names(**{"from": start, "to": end}), ["Bilal", "Zara"])
        self.assertEqual(self.names(**{"from": end, "to": start}), ["Bilal", "Zara"])  # swapped dates tolerated
        self.assertEqual(self.names(**{"from": "not-a-date"}), ["Ayesha", "Bilal", "Zara"])

    def test_payment_filter_and_totals(self):
        response = self.client.get(self.url, {"payment_status": "paid"})
        self.assertEqual([o.full_name for o in response.context["orders"]], ["Bilal"])
        self.assertEqual(response.context["filtered_value"], Decimal("9000"))

    def test_status_tab_counts_follow_other_filters(self):
        response = self.client.get(self.url, {"range": "7d"})
        counts = {value: n for value, _, n in response.context["status_counts"]}
        self.assertEqual(counts["pending"], 2)
        self.assertEqual(counts["delivered"], 0)  # the delivered order is 40 days old
        self.assertEqual(response.context["status_total"], 2)

    def test_copy_button_on_order_numbers(self):
        self.assertContains(self.client.get(self.url), f'data-copy="{self.a.number}"')


class OtherListSortingTests(TestCase):
    def setUp(self):
        self.client.force_login(make_vendor())

    def test_products_sorting(self):
        make_product(name="Alpha", price=Decimal("300"))
        make_product(name="Beta", price=Decimal("100"))
        response = self.client.get(reverse("dashboard:product_list"), {"sort": "price_asc"})
        self.assertEqual([p.name for p in response.context["products"]], ["Beta", "Alpha"])
        self.assertContains(response, 'aria-sort="ascending"')

    def test_inventory_and_expenses_and_appointments_accept_sort(self):
        for name, sort in (
            ("dashboard:inventory", "stock_desc"),
            ("dashboard:expense_list", "amount_desc"),
            ("dashboard:appointment_list", "client"),
        ):
            response = self.client.get(reverse(name), {"sort": sort, "range": "30d"})
            self.assertEqual(response.status_code, 200, name)
            self.assertEqual(response.context["sort"], sort, name)


class RememberMeTests(TestCase):
    def setUp(self):
        self.vendor = make_vendor(password="Vendor-pass-123")

    def login(self, remember):
        data = {"login": self.vendor.email, "password": "Vendor-pass-123"}
        if remember:
            data["remember"] = "on"
        self.client.post(reverse("account_login"), data)

    def age_session(self, seconds):
        session = self.client.session
        session[LAST_SEEN_KEY] = int(timezone.now().timestamp()) - seconds
        session.save()

    @override_settings(BROWSER_SESSION_IDLE_TIMEOUT=60)
    def test_unremembered_session_ends_after_inactivity(self):
        self.login(remember=False)
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 200)
        self.age_session(120)
        response = self.client.get(reverse("dashboard:overview"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])

    @override_settings(BROWSER_SESSION_IDLE_TIMEOUT=60)
    def test_remembered_session_survives_inactivity(self):
        self.login(remember=True)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.age_session(120)
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 200)

    def test_login_page_shows_forgot_password_once(self):
        html = self.client.get(reverse("account_login")).content.decode()
        self.assertEqual(html.lower().count("forgot"), 1)
