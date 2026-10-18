from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    VENDOR = "vendor", "Vendor"


class User(AbstractUser):
    """
    Application user. ``role`` separates shoppers (customers) from salon staff
    (vendors) who manage products, inventory, orders and appointments.
    Vendors are never created through public sign-up; use the admin or the
    ``createvendor`` management command.
    """

    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    phone = models.CharField(max_length=30, blank=True)

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return self.get_full_name() or self.email or self.username

    @property
    def is_vendor(self) -> bool:
        return self.is_active and (self.role == Role.VENDOR or self.is_superuser)

    @property
    def is_customer(self) -> bool:
        return self.role == Role.CUSTOMER

    @property
    def display_name(self) -> str:
        return self.first_name or self.get_full_name() or self.email.split("@")[0]
