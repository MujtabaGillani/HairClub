from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.core.testing import make_product


class CartTests(TestCase):
    def add(self, product, quantity=1, ajax=False):
        headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"} if ajax else {}
        return self.client.post(reverse("cart:add", args=[product.pk]), {"quantity": quantity}, **headers)

    def session_cart(self):
        return self.client.session.get(settings.CART_SESSION_KEY, {})

    def test_guest_can_add_and_view_cart(self):
        product = make_product(stock=5)
        response = self.add(product, 2)
        self.assertRedirects(response, reverse("cart:detail"))
        self.assertEqual(self.session_cart(), {str(product.pk): 2})
        page = self.client.get(reverse("cart:detail"))
        self.assertEqual(page.context["cart"].subtotal, product.final_price * 2)

    def test_ajax_add_returns_json_with_count(self):
        product = make_product(stock=5)
        data = self.add(product, 3, ajax=True).json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["cart_count"], 3)

    def test_quantity_is_clamped_to_stock(self):
        product = make_product(stock=3)
        self.add(product, 2)
        self.add(product, 2)
        self.assertEqual(self.session_cart(), {str(product.pk): 3})

    def test_cannot_add_hidden_price_or_out_of_stock_product(self):
        for product in (make_product(show_price=False), make_product(stock=0)):
            response = self.add(product, 1, ajax=True)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.session_cart(), {})

    def test_invalid_quantity_rejected(self):
        product = make_product()
        self.assertEqual(self.add(product, 0, ajax=True).status_code, 400)
        self.assertEqual(self.add(product, "abc", ajax=True).status_code, 400)

    def test_update_to_zero_removes_line(self):
        product = make_product()
        self.add(product, 2)
        self.client.post(reverse("cart:update", args=[product.pk]), {"quantity": 0})
        self.assertEqual(self.session_cart(), {})

    def test_remove(self):
        product = make_product()
        self.add(product)
        self.client.post(reverse("cart:remove", args=[product.pk]))
        self.assertEqual(self.session_cart(), {})

    def test_unavailable_products_are_dropped_from_cart(self):
        product = make_product()
        self.add(product)
        product.is_active = False
        product.save()
        response = self.client.get(reverse("cart:detail"))
        self.assertEqual(response.context["cart"].lines, [])
        self.assertEqual(self.session_cart(), {})

    def test_tampered_session_is_ignored(self):
        session = self.client.session
        session[settings.CART_SESSION_KEY] = {"abc": 5, "999999": 2}
        session.save()
        response = self.client.get(reverse("cart:detail"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cart"].lines, [])

    def test_next_redirect_rejects_external_hosts(self):
        product = make_product()
        response = self.client.post(
            reverse("cart:add", args=[product.pk]), {"quantity": 1, "next": "https://evil.example.com/"}
        )
        self.assertRedirects(response, reverse("cart:detail"))

    def test_add_requires_post(self):
        product = make_product()
        self.assertEqual(self.client.get(reverse("cart:add", args=[product.pk])).status_code, 405)
