from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Product
from apps.catalog.validators import validate_product_image
from apps.core.testing import image_file, make_category, make_product


class ProductModelTests(TestCase):
    def test_final_price_applies_discount_and_rounds(self):
        product = make_product(price=Decimal("999.99"), discount_percent=15)
        self.assertEqual(product.final_price, Decimal("849.99"))
        self.assertEqual(product.savings, Decimal("150.00"))
        self.assertTrue(product.has_discount)

    def test_no_discount_keeps_price(self):
        product = make_product(price=Decimal("1500.00"))
        self.assertEqual(product.final_price, Decimal("1500.00"))
        self.assertFalse(product.has_discount)

    def test_slug_and_sku_are_generated_and_unique(self):
        category = make_category()
        a = make_product(name="Lace Patch", category=category)
        b = make_product(name="Lace Patch", category=category)
        self.assertEqual(a.slug, "lace-patch")
        self.assertEqual(b.slug, "lace-patch-2")
        self.assertTrue(a.sku.startswith("HC-"))
        self.assertNotEqual(a.sku, b.sku)

    def test_purchasable_requires_active_price_and_stock(self):
        self.assertTrue(make_product(stock=1).is_purchasable)
        self.assertFalse(make_product(stock=0).is_purchasable)
        self.assertFalse(make_product(show_price=False).is_purchasable)
        self.assertFalse(make_product(is_active=False).is_purchasable)

    def test_stock_status(self):
        self.assertEqual(make_product(stock=0).stock_status, "out")
        self.assertEqual(make_product(stock=3, low_stock_threshold=5).stock_status, "low")
        self.assertEqual(make_product(stock=30).stock_status, "ok")

    def test_visible_excludes_unpublished_and_inactive_categories(self):
        visible = make_product()
        make_product(is_active=False)
        make_product(category=make_category(is_active=False))
        self.assertQuerySetEqual(Product.objects.visible(), [visible])

    def test_spec_rows_parse_label_value_lines(self):
        product = make_product(specifications="Base: Lace\nnot a spec line\nSize : 8x10\nEmpty:")
        self.assertEqual(product.spec_rows, [("Base", "Lace"), ("Size", "8x10")])


class ImageValidatorTests(TestCase):
    def test_accepts_real_jpeg(self):
        validate_product_image(image_file())

    def test_rejects_non_image(self):
        with self.assertRaises(ValidationError):
            validate_product_image(SimpleUploadedFile("evil.jpg", b"<?php echo 1; ?>", content_type="image/jpeg"))

    def test_rejects_disallowed_format(self):
        with self.assertRaises(ValidationError):
            validate_product_image(image_file("anim.gif", fmt="GIF"))

    @override_settings(PRODUCT_IMAGE_MAX_BYTES=100)
    def test_rejects_oversized_file(self):
        with self.assertRaises(ValidationError):
            validate_product_image(image_file(size=(200, 200)))


class ShopViewTests(TestCase):
    def test_list_filters_by_category_and_search(self):
        hair = make_category(name="Hair Patches")
        patch = make_product(name="Skin Patch", category=hair)
        make_product(name="Shampoo")
        response = self.client.get(reverse("catalog:product_list"), {"category": hair.slug})
        self.assertEqual(list(response.context["products"]), [patch])
        response = self.client.get(reverse("catalog:product_list"), {"q": "shamp"})
        self.assertEqual([p.name for p in response.context["products"]], ["Shampoo"])

    def test_sort_by_price_uses_discounted_price(self):
        cheap_after_discount = make_product(price=Decimal("2000"), discount_percent=60)  # 800
        mid = make_product(price=Decimal("1000"))
        response = self.client.get(reverse("catalog:product_list"), {"sort": "price_asc"})
        self.assertEqual(list(response.context["products"]), [cheap_after_discount, mid])

    def test_unpublished_product_detail_returns_404(self):
        product = make_product(is_active=False)
        self.assertEqual(self.client.get(product.get_absolute_url()).status_code, 404)

    def test_hidden_price_shows_whatsapp_enquiry_not_cart(self):
        product = make_product(show_price=False, price=Decimal("12345"))
        response = self.client.get(product.get_absolute_url())
        self.assertContains(response, "Price on request")
        self.assertContains(response, "https://wa.me/")
        self.assertNotContains(response, "12,345")
        self.assertNotContains(response, reverse("cart:add", args=[product.pk]))
