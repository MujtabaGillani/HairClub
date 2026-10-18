"""
Populate the database with demo categories, services and products so the
site can be explored and QA'd immediately. Safe to run more than once.
"""

import io
from decimal import Decimal

from django.contrib.sites.models import Site
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image, ImageDraw, ImageFont

from apps.appointments.models import Service
from apps.catalog.models import Category, Product, ProductImage
from apps.core.models import SiteSettings
from apps.inventory.models import MovementReason
from apps.inventory.services import adjust_stock

CATEGORIES = [
    ("Hair Patches", "stars", "Custom and ready-to-wear non-surgical hair systems."),
    ("Adhesives & Tapes", "droplet", "Professional bonding solutions for a secure, natural hold."),
    ("Hair Care", "flower1", "Shampoos, conditioners and treatments made for hair systems."),
    ("Styling", "wind", "Finishing products for a natural, matte look."),
    ("Accessories", "bag", "Brushes, stands and maintenance tools."),
]

SERVICES = [
    (
        "Free Consultation",
        "chat-heart",
        30,
        None,
        "Private one-to-one assessment of your hair loss and the right solution for you.",
    ),
    (
        "Non-Surgical Hair Replacement",
        "stars",
        120,
        Decimal("25000"),
        "Full custom hair system fitting, colour-matched, cut and styled to blend seamlessly.",
    ),
    (
        "Hair Patch Fitting",
        "patch-check",
        90,
        Decimal("8000"),
        "Professional fitting of a ready-to-wear or customer-supplied hair patch.",
    ),
    (
        "Maintenance & Re-bonding",
        "arrow-repeat",
        60,
        Decimal("4500"),
        "Deep clean, adhesive removal and secure re-bonding to keep your system flawless.",
    ),
    (
        "Cut & Style",
        "scissors",
        45,
        Decimal("2500"),
        "Precision cut and style for system wearers, blended with your natural hair.",
    ),
    (
        "Scalp Treatment",
        "droplet-half",
        45,
        Decimal("3500"),
        "Soothing exfoliation and treatment to keep your scalp healthy under a system.",
    ),
]

PRODUCTS = [
    # name, category, price, discount, stock, show_price, featured, brand, short, specs
    (
        "Ultra-Thin Skin Hair Patch 0.03mm",
        "Hair Patches",
        38000,
        10,
        12,
        True,
        True,
        "HairClub Pro",
        "Virtually invisible poly skin base for the most natural hairline.",
        'Base: 0.03mm poly skin\nHair type: 100% Remy human hair\nSize: 8" × 10"\n'
        "Density: 110% medium-light\nLifespan: 2–3 months",
    ),
    (
        "French Lace Hair System",
        "Hair Patches",
        45000,
        0,
        8,
        True,
        True,
        "HairClub Pro",
        "Breathable French lace with a bleached-knot front for summer comfort.",
        'Base: Swiss/French lace\nHair type: 100% Remy human hair\nSize: 8" × 10"\nDensity: 120%\nLifespan: 4–6 months',
    ),
    (
        "Mono Base Hair Patch",
        "Hair Patches",
        32000,
        0,
        4,
        True,
        False,
        "HairClub",
        "Durable fine mono base, ideal for first-time wearers.",
        'Base: Fine mono with poly perimeter\nHair type: Indian Remy\nSize: 7" × 9"\nLifespan: 6–12 months',
    ),
    (
        "Custom-Made Hair System",
        "Hair Patches",
        65000,
        0,
        3,
        False,
        True,
        "HairClub Bespoke",
        "Made to your exact template, colour and density. Price depends on specification.",
        "Base: Your choice\nHair type: European or Indian Remy\nLead time: 4–6 weeks",
    ),
    (
        "Ultra Hold Liquid Adhesive 1.4oz",
        "Adhesives & Tapes",
        4200,
        0,
        40,
        True,
        True,
        "Ultra Hold",
        "Long-lasting liquid bond for up to 4 weeks of secure wear.",
        "Hold: Up to 4 weeks\nVolume: 1.4 fl oz\nBest for: Lace and poly bases",
    ),
    (
        "Lace Front Support Tape (72 pcs)",
        "Adhesives & Tapes",
        2600,
        15,
        3,
        True,
        False,
        "Walker Tape",
        "Pre-cut contour strips for the front hairline.",
        "Count: 72 contour strips\nHold: 3–5 days",
    ),
    (
        "Sulfate-Free System Shampoo 300ml",
        "Hair Care",
        2200,
        0,
        25,
        True,
        False,
        "HairClub Care",
        "Gentle daily cleanser that protects colour and adhesive bonds.",
        "Volume: 300ml\nSulfate-free: Yes\nSuitable for: All hair systems",
    ),
    (
        "Deep Moisture Conditioner 300ml",
        "Hair Care",
        2400,
        0,
        0,
        True,
        False,
        "HairClub Care",
        "Restores softness and movement to human-hair systems.",
        "Volume: 300ml\nKey ingredients: Argan oil, keratin",
    ),
    (
        "Matte Texture Clay 85g",
        "Styling",
        1900,
        20,
        18,
        True,
        True,
        "HairClub Studio",
        "Medium hold, zero shine: the secret to a natural-looking system.",
        "Hold: Medium\nFinish: Matte\nWeight: 85g",
    ),
    (
        "Soft-Bristle System Brush",
        "Accessories",
        1500,
        0,
        30,
        True,
        False,
        "HairClub",
        "Wide-spaced soft bristles that detangle without stressing knots.",
        "",
    ),
]

PALETTE = [
    ((27, 26, 31), (196, 162, 122)),
    ((244, 235, 223), (138, 106, 59)),
    ((58, 55, 64), (244, 235, 223)),
]


def make_image(title: str, variant: int) -> ContentFile:
    bg, fg = PALETTE[variant % len(PALETTE)]
    img = Image.new("RGB", (900, 900), bg)
    draw = ImageDraw.Draw(img)
    for r in range(420, 120, -60):
        draw.ellipse((450 - r, 450 - r, 450 + r, 450 + r), outline=fg, width=2)
    try:
        font = ImageFont.truetype("georgia.ttf", 54)
        small = ImageFont.truetype("arial.ttf", 30)
    except OSError:
        font = small = ImageFont.load_default()
    words, lines, line = title.split(), [], ""
    for word in words:
        if len(line + " " + word) > 18:
            lines.append(line.strip())
            line = word
        else:
            line += " " + word
    lines.append(line.strip())
    y = 450 - len(lines) * 34
    for text in lines:
        w = draw.textlength(text, font=font)
        draw.text(((900 - w) / 2, y), text, fill=fg, font=font)
        y += 68
    label = "HAIRCLUB"
    draw.text(((900 - draw.textlength(label, font=small)) / 2, 790), label, fill=fg, font=small)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return ContentFile(buffer.getvalue(), name=f"demo-{variant}.jpg")


class Command(BaseCommand):
    help = "Load demo categories, services and products (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        Site.objects.update_or_create(pk=1, defaults={"domain": "localhost:8000", "name": "HairClub"})
        SiteSettings.load()

        categories = {}
        for order, (name, icon, desc) in enumerate(CATEGORIES):
            categories[name], _ = Category.objects.get_or_create(
                name=name, defaults={"icon": icon, "description": desc, "sort_order": order}
            )

        for order, (name, icon, minutes, price, desc) in enumerate(SERVICES):
            Service.objects.get_or_create(
                name=name,
                defaults={
                    "icon": icon,
                    "duration_minutes": minutes,
                    "starting_price": price,
                    "short_description": desc,
                    "description": desc,
                    "sort_order": order,
                },
            )

        created = 0
        for name, cat, price, discount, stock, show_price, featured, brand, short, specs in PRODUCTS:
            if Product.objects.filter(name=name).exists():
                continue
            product = Product.objects.create(
                name=name,
                category=categories[cat],
                price=Decimal(price),
                discount_percent=discount,
                show_price=show_price,
                is_featured=featured,
                brand=brand,
                short_description=short,
                description=f"{short}\n\nFitted and recommended by the {brand} specialists. "
                "Contact us on WhatsApp if you need help choosing the right option.",
                specifications=specs,
            )
            for variant in range(3 if cat == "Hair Patches" else 2):
                ProductImage.objects.create(
                    product=product,
                    image=make_image(name, variant),
                    alt_text=name,
                    is_primary=variant == 0,
                    sort_order=variant,
                )
            if stock:
                adjust_stock(product, stock, MovementReason.INITIAL, note="Demo data")
            created += 1

        if options["verbosity"]:
            self.stdout.write(self.style.SUCCESS(f"Demo data ready ({created} new products)."))
