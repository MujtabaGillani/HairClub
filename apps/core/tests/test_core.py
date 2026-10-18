from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Product
from apps.core.models import SiteSettings
from apps.core.templatetags.core_tags import money
from apps.core.whatsapp import build_whatsapp_url, normalize_phone


class WhatsAppTests(TestCase):
    def test_normalize_local_and_international_numbers(self):
        self.assertEqual(normalize_phone("0300 123-4567"), "923001234567")
        self.assertEqual(normalize_phone("+92 300 1234567"), "923001234567")
        self.assertEqual(normalize_phone("0092 300 1234567"), "923001234567")

    def test_url_encodes_message(self):
        url = build_whatsapp_url("923001234567", "Hi & bye\nnext line")
        self.assertEqual(url, "https://wa.me/923001234567?text=Hi%20%26%20bye%0Anext%20line")


class TemplateTagTests(TestCase):
    @override_settings(CURRENCY_SYMBOL="Rs.")
    def test_money_formatting(self):
        self.assertEqual(money(Decimal("12500.00")), "Rs. 12,500")
        self.assertEqual(money(Decimal("99.5")), "Rs. 99.50")
        self.assertEqual(money(Decimal("-4200")), "−Rs. 4,200")
        self.assertEqual(money(None), "")


class SiteSettingsTests(TestCase):
    def test_singleton(self):
        a = SiteSettings.load()
        a.business_name = "Changed"
        a.save()
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.load().business_name, "Changed")


class PublicPagesTests(TestCase):
    def test_public_pages_render(self):
        for name in (
            "core:home",
            "core:about",
            "core:contact",
            "catalog:product_list",
            "appointments:book",
            "appointments:services",
            "cart:detail",
            "orders:lookup",
            "account_login",
            "account_signup",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo", verbosity=0)
        count = Product.objects.count()
        call_command("seed_demo", verbosity=0)
        self.assertEqual(Product.objects.count(), count)
        self.assertGreater(count, 0)
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)
