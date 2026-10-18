from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.core.models import SiteSettings
from apps.core.testing import make_product, make_user
from apps.inventory.models import MovementReason, StockMovement
from apps.orders.models import Order, OrderStatus, PaymentStatus
from apps.orders.services import InvalidTransition, calculate_shipping, change_order_status

CHECKOUT_DATA = {
    "full_name": "Ali Khan",
    "email": "ali@example.com",
    "phone": "0300 1234567",
    "shipping_method": "standard",
    "address_line1": "12 Main Boulevard",
    "city": "Lahore",
    "province": "Punjab",
    "payment_method": "cod",
}


class CheckoutTests(TestCase):
    def setUp(self):
        site = SiteSettings.load()
        site.standard_shipping_fee = Decimal("250")
        site.express_shipping_fee = Decimal("500")
        site.free_shipping_threshold = Decimal("10000")
        site.save()

    def add_to_cart(self, product, qty):
        self.client.post(reverse("cart:add", args=[product.pk]), {"quantity": qty})

    def checkout(self, **overrides):
        return self.client.post(reverse("orders:checkout"), {**CHECKOUT_DATA, **overrides})

    def test_empty_cart_redirects_to_cart(self):
        self.assertRedirects(self.client.get(reverse("orders:checkout")), reverse("cart:detail"))

    def test_guest_checkout_creates_order_and_decrements_stock(self):
        product = make_product(price=Decimal("1000"), discount_percent=10, stock=5)
        self.add_to_cart(product, 2)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.checkout()

        order = Order.objects.get()
        self.assertRedirects(response, reverse("orders:confirmation", args=[order.number]))
        self.assertIsNone(order.user)
        self.assertEqual(order.subtotal, Decimal("1800.00"))
        self.assertEqual(order.shipping_cost, Decimal("250"))
        self.assertEqual(order.total, Decimal("2050.00"))
        self.assertEqual(order.status, OrderStatus.PENDING)
        item = order.items.get()
        self.assertEqual((item.product_name, item.unit_price, item.quantity), (product.name, Decimal("900.00"), 2))

        product.refresh_from_db()
        self.assertEqual(product.stock, 3)
        movement = StockMovement.objects.get(reason=MovementReason.SALE)
        self.assertEqual((movement.quantity_change, movement.reference), (-2, order.number))

        self.assertEqual(self.client.session.get("cart"), {})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(order.number, mail.outbox[0].subject)

        self.assertEqual(self.client.get(order.get_absolute_url()).status_code, 200)

    def test_signed_in_checkout_links_order_to_user(self):
        user = make_user()
        self.client.force_login(user)
        self.add_to_cart(make_product(), 1)
        self.checkout()
        self.assertEqual(Order.objects.get().user, user)

    def test_price_is_read_from_database_not_session(self):
        product = make_product(price=Decimal("1000"))
        self.add_to_cart(product, 1)
        product.price = Decimal("1500")
        product.save()
        self.checkout()
        self.assertEqual(Order.objects.get().subtotal, Decimal("1500.00"))

    def test_stock_sold_out_between_cart_and_checkout(self):
        product = make_product(stock=2)
        self.add_to_cart(product, 2)
        Product = type(product)
        Product.objects.filter(pk=product.pk).update(stock=1)
        # Cart clamps to available stock when re-read, so the order uses 1 unit.
        self.checkout()
        self.assertEqual(Order.objects.get().items.get().quantity, 1)
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)

    def test_product_removed_before_checkout_blocks_order(self):
        product = make_product(stock=2)
        self.add_to_cart(product, 1)
        type(product).objects.filter(pk=product.pk).update(stock=0)
        response = self.checkout()
        self.assertFalse(Order.objects.exists())
        self.assertRedirects(response, reverse("cart:detail"))

    def test_delivery_requires_address_but_pickup_does_not(self):
        self.add_to_cart(make_product(), 1)
        response = self.checkout(address_line1="", city="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("address_line1", response.context["form"].errors)
        self.assertFalse(Order.objects.exists())

        self.checkout(shipping_method="pickup", address_line1="", city="", province="")
        order = Order.objects.get()
        self.assertEqual(order.shipping_cost, Decimal("0.00"))

    def test_invalid_phone_rejected(self):
        self.add_to_cart(make_product(), 1)
        response = self.checkout(phone="123")
        self.assertIn("phone", response.context["form"].errors)

    def test_other_visitors_cannot_view_order(self):
        self.add_to_cart(make_product(), 1)
        self.checkout()
        order = Order.objects.get()
        self.client.logout()
        self.client.cookies.clear()
        self.assertEqual(self.client.get(order.get_absolute_url()).status_code, 404)

    def test_lookup_grants_access_with_matching_email(self):
        self.add_to_cart(make_product(), 1)
        self.checkout()
        order = Order.objects.get()
        self.client.cookies.clear()
        url = reverse("orders:lookup")
        wrong = self.client.get(url, {"number": order.number, "email": "nope@example.com"})
        self.assertEqual(wrong.status_code, 200)
        right = self.client.get(url, {"number": order.number.lower(), "email": "ALI@example.com"})
        self.assertRedirects(right, order.get_absolute_url())

    def test_customer_can_cancel_pending_order_and_stock_returns(self):
        product = make_product(stock=5)
        self.add_to_cart(product, 2)
        self.checkout()
        order = Order.objects.get()
        self.client.post(reverse("orders:cancel", args=[order.number]))
        order.refresh_from_db()
        self.assertIsNone(order.events.first().created_by)
        product.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertEqual(product.stock, 5)


class OrderServiceTests(TestCase):
    def test_shipping_rules(self):
        site = SiteSettings.load()
        site.free_shipping_threshold = Decimal("5000")
        site.save()
        self.assertEqual(calculate_shipping(Decimal("4999"), "standard"), site.standard_shipping_fee)
        self.assertEqual(calculate_shipping(Decimal("5000"), "standard"), Decimal("0"))
        self.assertEqual(calculate_shipping(Decimal("9000"), "express"), site.express_shipping_fee)
        self.assertEqual(calculate_shipping(Decimal("100"), "pickup"), Decimal("0"))

    def _order(self, **extra):
        return Order.objects.create(
            full_name="A", email="a@example.com", phone="03001234567", subtotal=1, total=1, **extra
        )

    def test_invalid_transition_raises(self):
        order = self._order()
        with self.assertRaises(InvalidTransition):
            change_order_status(order, OrderStatus.DELIVERED)

    def test_delivering_cod_order_marks_it_paid(self):
        order = self._order(status=OrderStatus.SHIPPED)
        order = change_order_status(order, OrderStatus.DELIVERED)
        self.assertEqual(order.payment_status, PaymentStatus.PAID)
        self.assertEqual(order.events.first().status, OrderStatus.DELIVERED)
