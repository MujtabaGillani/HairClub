"""Shared factories for the test-suite (kept dependency-free on purpose)."""

import io
import itertools
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import Role, User
from apps.appointments.models import Service
from apps.catalog.models import Category, Product, ProductImage

_seq = itertools.count(1)


def image_file(name: str = "photo.jpg", size=(20, 20), fmt: str = "JPEG") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", size, (196, 162, 122)).save(buffer, format=fmt)
    content_type = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}[fmt]
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


def make_user(*, role: str = Role.CUSTOMER, password: str = "pass-12345!", **extra) -> User:
    n = next(_seq)
    email = extra.pop("email", f"user{n}@example.com")
    return User.objects.create_user(username=email, email=email, password=password, role=role, **extra)


def make_vendor(**extra) -> User:
    return make_user(role=Role.VENDOR, **extra)


def make_category(**extra) -> Category:
    n = next(_seq)
    return Category.objects.create(name=extra.pop("name", f"Category {n}"), **extra)


def make_product(*, stock: int = 10, with_image: bool = True, **extra) -> Product:
    n = next(_seq)
    defaults = {
        "name": f"Product {n}",
        "category": extra.pop("category", None) or make_category(),
        "price": Decimal("1000.00"),
        "description": "A product.",
    }
    defaults.update(extra)
    product = Product.objects.create(stock=stock, **defaults)
    if with_image:
        ProductImage.objects.create(product=product, image=image_file(), is_primary=True)
    return product


def make_service(**extra) -> Service:
    n = next(_seq)
    defaults = {"name": f"Service {n}", "short_description": "A treatment.", "duration_minutes": 60}
    defaults.update(extra)
    return Service.objects.create(**defaults)
