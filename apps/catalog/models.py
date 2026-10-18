import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Prefetch, Q
from django.urls import reverse
from django.utils.text import slugify

from apps.core.models import TimeStampedModel

from .validators import validate_product_image

TWO_PLACES = Decimal("0.01")


def unique_slugify(instance, value: str, slug_field: str = "slug", max_length: int = 200) -> str:
    base = slugify(value)[: max_length - 9] or uuid.uuid4().hex[:8]
    slug = base
    model = type(instance)
    counter = 2
    while model.objects.filter(**{slug_field: slug}).exclude(pk=instance.pk).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


class CategoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=40, blank=True, default="bag", help_text="Bootstrap icon name, e.g. 'stars' or 'droplet'."
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name, max_length=120)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f"{reverse('catalog:product_list')}?category={self.slug}"


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def visible(self):
        """Products a shopper is allowed to see."""
        return self.filter(is_active=True, category__is_active=True)

    def with_images(self):
        return self.select_related("category").prefetch_related(
            Prefetch("images", queryset=ProductImage.objects.order_by("-is_primary", "sort_order", "pk"))
        )

    def low_stock(self):
        return self.filter(stock__gt=0, stock__lte=models.F("low_stock_threshold"))

    def out_of_stock(self):
        return self.filter(stock=0)

    def search(self, term: str):
        term = (term or "").strip()
        if not term:
            return self
        return self.filter(
            Q(name__icontains=term)
            | Q(sku__icontains=term)
            | Q(short_description__icontains=term)
            | Q(brand__icontains=term)
        )


class Product(TimeStampedModel):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    sku = models.CharField("SKU", max_length=40, unique=True, blank=True)
    brand = models.CharField(max_length=80, blank=True)
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    specifications = models.TextField(
        blank=True,
        help_text="One per line as 'Label: value', e.g. 'Base: Fine mono lace'.",
    )

    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    discount_percent = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(90)],
        help_text="Optional percentage off (0–90).",
    )
    show_price = models.BooleanField(
        default=True,
        help_text="When hidden, shoppers see 'Price on request' and must enquire on WhatsApp.",
    )

    stock = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveSmallIntegerField(default=5)

    is_active = models.BooleanField("published", default=True, db_index=True)
    is_featured = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["is_active", "category"]), models.Index(fields=["stock"])]
        constraints = [
            models.CheckConstraint(condition=Q(discount_percent__lte=90), name="product_discount_lte_90"),
            models.CheckConstraint(condition=Q(price__gt=0), name="product_price_positive"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name, max_length=220)
        if not self.sku:
            self.sku = f"HC-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:product_detail", kwargs={"slug": self.slug})

    # --- Pricing -----------------------------------------------------------
    @property
    def has_discount(self) -> bool:
        return self.discount_percent > 0

    @property
    def final_price(self) -> Decimal:
        multiplier = (Decimal(100) - Decimal(self.discount_percent)) / Decimal(100)
        return (self.price * multiplier).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    @property
    def savings(self) -> Decimal:
        return self.price - self.final_price

    # --- Availability ------------------------------------------------------
    @property
    def in_stock(self) -> bool:
        return self.stock > 0

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.stock <= self.low_stock_threshold

    @property
    def stock_status(self) -> str:
        if self.stock == 0:
            return "out"
        return "low" if self.is_low_stock else "ok"

    @property
    def is_purchasable(self) -> bool:
        """Only published, priced, in-stock products can go in the cart."""
        return self.is_active and self.show_price and self.in_stock

    # --- Media -------------------------------------------------------------
    @property
    def primary_image(self):
        images = list(self.images.all())  # uses prefetch cache when available
        if not images:
            return None
        return next((img for img in images if img.is_primary), images[0])

    @property
    def spec_rows(self) -> list[tuple[str, str]]:
        rows = []
        for line in self.specifications.splitlines():
            if ":" in line:
                label, value = line.split(":", 1)
                if label.strip() and value.strip():
                    rows.append((label.strip(), value.strip()))
        return rows


def product_image_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"products/{instance.product_id or 'new'}/{uuid.uuid4().hex}.{ext}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=product_image_path, validators=[validate_product_image])
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "sort_order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"], condition=Q(is_primary=True), name="one_primary_image_per_product"
            )
        ]

    def __str__(self):
        return f"Image for {self.product}"

    @property
    def alt(self) -> str:
        return self.alt_text or self.product.name
