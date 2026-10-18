from django.test import TestCase
from django.urls import reverse

from apps.core.testing import make_product, make_user
from apps.wishlist.models import WishlistItem


class WishlistTests(TestCase):
    def test_anonymous_user_is_sent_to_login(self):
        product = make_product()
        response = self.client.post(reverse("wishlist:toggle", args=[product.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])

        ajax = self.client.post(reverse("wishlist:toggle", args=[product.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(ajax.status_code, 401)
        self.assertIn("login_url", ajax.json())

    def test_toggle_adds_then_removes(self):
        user = make_user()
        product = make_product()
        self.client.force_login(user)
        url = reverse("wishlist:toggle", args=[product.pk])

        first = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()
        self.assertTrue(first["in_wishlist"])
        self.assertEqual(first["wishlist_count"], 1)

        second = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest").json()
        self.assertFalse(second["in_wishlist"])
        self.assertFalse(WishlistItem.objects.exists())

    def test_list_shows_only_own_items(self):
        me, other = make_user(), make_user()
        mine, theirs = make_product(), make_product()
        WishlistItem.objects.create(user=me, product=mine)
        WishlistItem.objects.create(user=other, product=theirs)
        self.client.force_login(me)
        response = self.client.get(reverse("wishlist:list"))
        self.assertEqual([i.product for i in response.context["items"]], [mine])
