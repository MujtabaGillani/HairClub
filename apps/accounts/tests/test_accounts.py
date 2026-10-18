from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.core.testing import make_user


class SignupTests(TestCase):
    def test_signup_creates_customer_with_profile_fields(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "first_name": "Usman",
                "last_name": "Raza",
                "phone": "03001234567",
                "email": "usman@example.com",
                "password1": "Strong-pass-2026",
                "password2": "Strong-pass-2026",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="usman@example.com")
        self.assertEqual((user.first_name, user.last_name, user.phone), ("Usman", "Raza", "03001234567"))
        self.assertEqual(user.role, Role.CUSTOMER)
        self.assertFalse(user.is_vendor)

    def test_signup_cannot_self_assign_vendor_role(self):
        self.client.post(
            reverse("account_signup"),
            {
                "first_name": "Eve",
                "email": "eve@example.com",
                "password1": "Strong-pass-2026",
                "password2": "Strong-pass-2026",
                "role": "vendor",
            },
        )
        self.assertEqual(User.objects.get(email="eve@example.com").role, Role.CUSTOMER)


class AccountPagesTests(TestCase):
    def test_pages_require_login(self):
        for name in ("accounts:overview", "accounts:profile", "accounts:orders", "accounts:appointments"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302, name)

    def test_customer_redirect_and_profile_update(self):
        user = make_user()
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("accounts:redirect")), reverse("accounts:overview"))
        self.client.post(reverse("accounts:profile"), {"first_name": "Zara", "last_name": "", "phone": "0300"})
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Zara")


class CreateVendorCommandTests(TestCase):
    def test_creates_new_vendor(self):
        call_command("createvendor", email="Owner@Example.com", password="Owner-pass-2026", verbosity=0)
        user = User.objects.get(email="owner@example.com")
        self.assertTrue(user.is_vendor)
        self.assertTrue(user.check_password("Owner-pass-2026"))

    def test_promotes_existing_user(self):
        user = make_user()
        call_command("createvendor", email=user.email, verbosity=0)
        user.refresh_from_db()
        self.assertEqual(user.role, Role.VENDOR)
