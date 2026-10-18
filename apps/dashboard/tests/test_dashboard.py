from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus
from apps.catalog.models import Product, ProductImage
from apps.core.models import SiteSettings
from apps.core.testing import image_file, make_category, make_product, make_service, make_user, make_vendor
from apps.inventory.models import MovementReason, StockMovement
from apps.orders.models import Order, OrderItem, OrderStatus, PaymentStatus

DASHBOARD_URLS = [
    "dashboard:overview",
    "dashboard:product_list",
    "dashboard:product_create",
    "dashboard:inventory",
    "dashboard:stock_history",
    "dashboard:appointment_list",
    "dashboard:order_list",
    "dashboard:service_list",
    "dashboard:service_create",
    "dashboard:settings",
]


class AccessControlTests(TestCase):
    def test_anonymous_users_are_redirected_to_login(self):
        for name in DASHBOARD_URLS:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("account_login"), response["Location"])

    def test_customers_get_403(self):
        self.client.force_login(make_user())
        for name in DASHBOARD_URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_customers_cannot_post_vendor_actions(self):
        product = make_product(stock=5)
        self.client.force_login(make_user())
        response = self.client.post(
            reverse("dashboard:stock_adjust", args=[product.pk]), {"mode": "set", "quantity": 0}
        )
        self.assertEqual(response.status_code, 403)
        product.refresh_from_db()
        self.assertEqual(product.stock, 5)

    def test_vendors_can_access_everything(self):
        self.client.force_login(make_vendor())
        for name in DASHBOARD_URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_vendor_login_redirects_to_dashboard(self):
        vendor = make_vendor(password="Vendor-pass-123")
        response = self.client.post(reverse("account_login"), {"login": vendor.email, "password": "Vendor-pass-123"})
        self.assertRedirects(response, reverse("accounts:redirect"), target_status_code=302)
        self.assertRedirects(self.client.get(reverse("accounts:redirect")), reverse("dashboard:overview"))


class VendorTestCase(TestCase):
    def setUp(self):
        self.vendor = make_vendor()
        self.client.force_login(self.vendor)


@override_settings(PRODUCT_MIN_IMAGES=1, PRODUCT_MAX_IMAGES=3)
class ProductManagementTests(VendorTestCase):
    def product_data(self, **overrides):
        data = {
            "name": "Lace Hair System",
            "category": make_category().pk,
            "short_description": "Breathable lace",
            "description": "Full description",
            "price": "45000",
            "discount_percent": "10",
            "show_price": "on",
            "initial_stock": "7",
            "low_stock_threshold": "2",
            "is_active": "on",
        }
        data.update(overrides)
        return data

    def test_create_product_with_images_and_opening_stock(self):
        response = self.client.post(
            reverse("dashboard:product_create"),
            {
                **self.product_data(),
                "new_images": [image_file("a.jpg"), image_file("b.png", fmt="PNG")],
                "primary_image": "new-1",
            },
        )
        self.assertRedirects(response, reverse("dashboard:product_list"))
        product = Product.objects.get()
        self.assertEqual(product.stock, 7)
        self.assertEqual(product.final_price, Decimal("40500.00"))
        self.assertEqual(product.created_by, self.vendor)
        self.assertEqual(product.images.count(), 2)
        self.assertEqual(product.images.get(is_primary=True).sort_order, 1)
        movement = StockMovement.objects.get()
        self.assertEqual((movement.reason, movement.quantity_change), (MovementReason.INITIAL, 7))

    def test_create_requires_at_least_min_images(self):
        response = self.client.post(reverse("dashboard:product_create"), self.product_data())
        self.assertEqual(response.status_code, 200)
        self.assertIn("new_images", response.context["form"].errors)
        self.assertFalse(Product.objects.exists())

    def test_cannot_exceed_max_images(self):
        files = [image_file(f"{i}.jpg") for i in range(4)]
        response = self.client.post(reverse("dashboard:product_create"), {**self.product_data(), "new_images": files})
        self.assertIn("new_images", response.context["form"].errors)

    def test_rejects_non_image_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        bad = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        response = self.client.post(reverse("dashboard:product_create"), {**self.product_data(), "new_images": [bad]})
        self.assertIn("new_images", response.context["form"].errors)

    def test_update_removes_image_and_keeps_a_primary(self):
        product = make_product(stock=3)
        extra = ProductImage.objects.create(product=product, image=image_file())
        primary = product.images.get(is_primary=True)
        data = self.product_data(name="Renamed", category=product.category.pk)
        data.pop("initial_stock")
        data["remove_images"] = [primary.pk]
        response = self.client.post(reverse("dashboard:product_update", args=[product.pk]), data)
        self.assertRedirects(response, reverse("dashboard:product_list"))
        product.refresh_from_db()
        self.assertEqual(product.name, "Renamed")
        self.assertEqual(product.stock, 3, "stock must not change from the product form")
        self.assertEqual(list(product.images.all()), [extra])
        extra.refresh_from_db()
        self.assertTrue(extra.is_primary)

    def test_cannot_remove_last_image(self):
        product = make_product()
        data = self.product_data(category=product.category.pk)
        data.pop("initial_stock")
        data["remove_images"] = [product.images.get().pk]
        response = self.client.post(reverse("dashboard:product_update", args=[product.pk]), data)
        self.assertIn("new_images", response.context["form"].errors)

    def test_duplicate_sku_rejected(self):
        make_product(sku="HC-TAKEN")
        response = self.client.post(
            reverse("dashboard:product_create"), {**self.product_data(sku="hc-taken"), "new_images": [image_file()]}
        )
        self.assertIn("sku", response.context["form"].errors)

    def test_toggle_price_visibility(self):
        product = make_product(show_price=True)
        self.client.post(reverse("dashboard:product_toggle", args=[product.pk, "show_price"]))
        product.refresh_from_db()
        self.assertFalse(product.show_price)

    def test_toggle_unknown_field_is_ignored(self):
        product = make_product()
        self.client.post(reverse("dashboard:product_toggle", args=[product.pk, "price"]))
        product.refresh_from_db()
        self.assertEqual(product.price, Decimal("1000.00"))

    def test_delete_product_keeps_order_history(self):
        product = make_product()
        order = Order.objects.create(full_name="A", email="a@example.com", phone="0300", subtotal=1, total=1)
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            sku=product.sku,
            unit_price=1,
            quantity=1,
            line_total=1,
        )
        self.client.post(reverse("dashboard:product_delete", args=[product.pk]))
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
        self.assertEqual(order.items.get().product_name, product.name)


class InventoryTests(VendorTestCase):
    def adjust(self, product, **data):
        return self.client.post(reverse("dashboard:stock_adjust", args=[product.pk]), data)

    def test_add_remove_and_set(self):
        product = make_product(stock=5)
        self.adjust(product, mode="add", quantity=10, reason="restock", note="Invoice 42")
        product.refresh_from_db()
        self.assertEqual(product.stock, 15)
        self.adjust(product, mode="remove", quantity=3, reason="damaged")
        product.refresh_from_db()
        self.assertEqual(product.stock, 12)
        self.adjust(product, mode="set", quantity=4, reason="correction")
        product.refresh_from_db()
        self.assertEqual(product.stock, 4)
        changes = list(StockMovement.objects.order_by("pk").values_list("quantity_change", "stock_after"))
        self.assertEqual(changes, [(10, 15), (-3, 12), (-8, 4)])
        self.assertEqual(StockMovement.objects.first().created_by, self.vendor)

    def test_cannot_remove_more_than_in_stock(self):
        product = make_product(stock=2)
        self.adjust(product, mode="remove", quantity=5, reason="damaged")
        product.refresh_from_db()
        self.assertEqual(product.stock, 2)
        self.assertFalse(StockMovement.objects.exists())

    def test_low_stock_filter(self):
        low = make_product(stock=1, low_stock_threshold=5)
        make_product(stock=50)
        response = self.client.get(reverse("dashboard:inventory"), {"stock": "low"})
        self.assertEqual(list(response.context["products"]), [low])


class AppointmentManagementTests(VendorTestCase):
    def setUp(self):
        super().setUp()
        self.appointment = Appointment.objects.create(
            full_name="Bilal",
            phone="03001234567",
            service=make_service(),
            date=timezone.localdate() + timedelta(days=2),
            time=time(12, 0),
        )

    def test_pending_view_lists_new_requests(self):
        response = self.client.get(reverse("dashboard:appointment_list"), {"view": "pending"})
        self.assertEqual(list(response.context["appointments"]), [self.appointment])

    def test_confirm_records_staff_and_offers_whatsapp_notification(self):
        url = reverse("dashboard:appointment_status", args=[self.appointment.reference])
        response = self.client.post(url, {"status": "confirmed", "note": "See you"})
        self.assertRedirects(
            response,
            reverse("dashboard:appointment_detail", args=[self.appointment.reference]),
            fetch_redirect_response=False,
        )
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, AppointmentStatus.CONFIRMED)
        self.assertEqual(self.appointment.handled_by, self.vendor)

        detail = self.client.get(response["Location"])
        self.assertTrue(detail.context["notify_whatsapp_url"].startswith("https://wa.me/923001234567?text="))

    def test_disallowed_transition_is_rejected(self):
        url = reverse("dashboard:appointment_status", args=[self.appointment.reference])
        self.client.post(url, {"status": "completed"})
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, AppointmentStatus.PENDING)


class OrderManagementTests(VendorTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(stock=3)
        self.order = Order.objects.create(
            full_name="Hina",
            email="hina@example.com",
            phone="0300",
            subtotal=2000,
            total=2000,
            payment_method="bank_transfer",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            sku=self.product.sku,
            unit_price=1000,
            quantity=2,
            line_total=2000,
        )

    def post_status(self, status, **extra):
        return self.client.post(
            reverse("dashboard:order_status", args=[self.order.number]), {"status": status, **extra}
        )

    def test_vendor_moves_order_through_workflow(self):
        self.post_status("confirmed")
        self.post_status("shipped", tracking_number="TCS-123")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.SHIPPED)
        self.assertEqual(self.order.tracking_number, "TCS-123")
        self.assertEqual(self.order.events.count(), 2)

    def test_cancel_returns_stock(self):
        self.post_status("cancelled")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertTrue(StockMovement.objects.filter(reason=MovementReason.ORDER_CANCELLED, quantity_change=2).exists())

    def test_mark_paid(self):
        self.client.post(reverse("dashboard:order_mark_paid", args=[self.order.number]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)


class SettingsTests(VendorTestCase):
    def test_save_settings_including_closed_days(self):
        site = SiteSettings.load()
        form = self.client.get(reverse("dashboard:settings")).context["form"]
        data = {name: field.value() for name, field in ((n, form[n]) for n in form.fields) if field.value() is not None}
        data.update(
            whatsapp_number="923339998877",
            opening_time="09:00",
            closing_time="18:00",
            closed_days=["6"],
        )
        response = self.client.post(reverse("dashboard:settings"), data)
        self.assertRedirects(response, reverse("dashboard:settings"))
        site.refresh_from_db()
        self.assertEqual(site.whatsapp_number, "923339998877")
        self.assertEqual(site.closed_weekday_list, [6])

    def test_invalid_whatsapp_number_and_hours_rejected(self):
        form = self.client.get(reverse("dashboard:settings")).context["form"]
        data = {name: form[name].value() for name in form.fields if form[name].value() is not None}
        data.update(whatsapp_number="+92 300", opening_time="18:00", closing_time="09:00")
        response = self.client.post(reverse("dashboard:settings"), data)
        errors = response.context["form"].errors
        self.assertIn("whatsapp_number", errors)
        self.assertIn("closing_time", errors)
