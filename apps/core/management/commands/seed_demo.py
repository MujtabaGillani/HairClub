"""
Populate the database with demo categories, services, products, appointments
and orders so the site can be explored and QA'd immediately. Safe to run more
than once: appointments and orders are only added when none exist yet.
"""

import io
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.sites.models import Site
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from apps.accounts.models import Role, User
from apps.appointments.models import Appointment, Service
from apps.catalog.models import Category, Product, ProductImage
from apps.core.models import SiteSettings
from apps.inventory.models import MovementReason, StockMovement
from apps.inventory.services import adjust_stock
from apps.orders.models import Order, OrderEvent, OrderItem, PaymentMethod
from apps.orders.services import calculate_shipping, change_order_status, mark_order_paid

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
    help = "Load demo categories, services, products, appointments and orders (idempotent)."

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

        appointments = 0 if Appointment.objects.exists() else seed_appointments()
        orders = 0 if Order.objects.exists() else seed_orders()

        if options["verbosity"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Demo data ready ({created} new products, {appointments} appointments, {orders} orders)."
                )
            )


# --- Activity: appointments & orders ---------------------------------------
# Only created when the respective table is empty, so real data is never mixed
# with demo records on a re-run.

CUSTOMERS = [
    ("Ahmed Raza", "0300 4512378", "ahmed.raza@example.com", "House 14, Street 7, DHA Phase 5", "Lahore", "Punjab"),
    ("Bilal Hussain", "0321 7788123", "bilal.h@example.com", "Flat 3B, Clifton Block 2", "Karachi", "Sindh"),
    ("Usman Tariq", "0333 2219087", "usman.tariq@example.com", "22-C, F-8/3", "Islamabad", "ICT"),
    ("Hamza Sheikh", "0345 6671234", "", "Model Town Extension, Block D", "Lahore", "Punjab"),
    ("Faisal Qureshi", "0312 9081726", "faisal.q@example.com", "Satellite Town, Street 12", "Rawalpindi", "Punjab"),
    ("Imran Malik", "0301 5566778", "imran.malik@example.com", "Peoples Colony No. 1", "Faisalabad", "Punjab"),
    ("Zain Abbas", "0322 3344556", "", "Gulshan-e-Iqbal, Block 13-D", "Karachi", "Sindh"),
    ("Saad Butt", "0334 8899001", "saad.butt@example.com", "Cantt, Abid Majeed Road", "Lahore", "Punjab"),
    ("Kamran Javed", "0306 1122334", "kamran.j@example.com", "University Town, Phase 2", "Peshawar", "KPK"),
    ("Danish Iqbal", "0315 6677889", "danish.iqbal@example.com", "Wapda Town, Block K", "Multan", "Punjab"),
]

# (day offset from today, time, customer index, service, status, client notes, internal note)
APPOINTMENTS = [
    (-21, "12:00", 0, "Free Consultation", "completed", "Thinning at the crown for 3 years.", "Recommended skin base."),
    (-18, "15:30", 1, "Non-Surgical Hair Replacement", "completed", "", "Fitted 0.03mm skin, colour 1B."),
    (-14, "11:30", 2, "Hair Patch Fitting", "completed", "Bringing my own patch.", ""),
    (-12, "17:00", 3, "Free Consultation", "no_show", "", "Not reachable on phone."),
    (-9, "13:00", 4, "Maintenance & Re-bonding", "completed", "", "Re-bonded, adhesive switched to Ultra Hold."),
    (-7, "16:00", 5, "Cut & Style", "cancelled", "", "Client rescheduled by phone."),
    (-5, "12:30", 1, "Maintenance & Re-bonding", "completed", "Two weeks since fitting.", ""),
    (-3, "18:00", 6, "Scalp Treatment", "completed", "Itching under the system.", ""),
    (-1, "14:00", 7, "Free Consultation", "completed", "Interested in lace systems.", "Sent lace options on WhatsApp."),
    (0, "15:00", 8, "Hair Patch Fitting", "confirmed", "", ""),
    (0, "17:30", 0, "Cut & Style", "confirmed", "Blend with the sides please.", ""),
    (0, "19:00", 9, "Free Consultation", "pending", "Can I come after work?", ""),
    (1, "12:00", 2, "Maintenance & Re-bonding", "confirmed", "", ""),
    (1, "16:30", 3, "Free Consultation", "pending", "Rebooking, sorry for missing last time.", ""),
    (2, "11:00", 4, "Scalp Treatment", "pending", "", ""),
    (3, "13:30", 5, "Non-Surgical Hair Replacement", "confirmed", "Wedding next month, need natural look.", ""),
    (4, "18:30", 6, "Maintenance & Re-bonding", "pending", "", ""),
    (6, "14:30", 7, "Non-Surgical Hair Replacement", "pending", "Want the French lace system.", ""),
    (8, "12:00", 8, "Cut & Style", "pending", "", ""),
    (12, "15:00", 9, "Hair Patch Fitting", "pending", "First time, a bit nervous.", ""),
]

# (days ago, customer index, [(product name, qty)], shipping, payment, statuses to walk through, tracking)
ORDERS = [
    (
        28,
        0,
        [("Ultra Hold Liquid Adhesive 1.4oz", 2), ("Sulfate-Free System Shampoo 300ml", 1)],
        "standard",
        "cod",
        ["confirmed", "shipped", "delivered"],
        "TCS-7781245",
    ),
    (
        25,
        2,
        [("French Lace Hair System", 1)],
        "express",
        "bank_transfer",
        ["confirmed", "processing", "shipped", "delivered"],
        "LEO-55120983",
    ),
    (
        21,
        4,
        [("Matte Texture Clay 85g", 2), ("Soft-Bristle System Brush", 1)],
        "standard",
        "cod",
        ["confirmed", "shipped", "delivered"],
        "TCS-7790031",
    ),
    (
        17,
        6,
        [("Ultra-Thin Skin Hair Patch 0.03mm", 1), ("Ultra Hold Liquid Adhesive 1.4oz", 1)],
        "express",
        "cod",
        ["confirmed", "shipped", "delivered"],
        "LEO-55170266",
    ),
    (14, 1, [("Sulfate-Free System Shampoo 300ml", 2)], "standard", "bank_transfer", ["cancelled"], ""),
    (
        11,
        8,
        [("Lace Front Support Tape (72 pcs)", 1), ("Matte Texture Clay 85g", 1)],
        "standard",
        "cod",
        ["confirmed", "shipped", "delivered"],
        "MNP-3301187",
    ),
    (8, 3, [("Mono Base Hair Patch", 1)], "express", "cod", ["confirmed", "shipped"], "LEO-55188410"),
    (
        6,
        9,
        [("Ultra Hold Liquid Adhesive 1.4oz", 1), ("Soft-Bristle System Brush", 1)],
        "standard",
        "bank_transfer",
        ["confirmed", "processing"],
        "",
    ),
    (4, 5, [("Matte Texture Clay 85g", 3)], "standard", "cod", ["confirmed"], ""),
    (2, 7, [("Ultra-Thin Skin Hair Patch 0.03mm", 1)], "standard", "bank_transfer", [], ""),
    (1, 0, [("Sulfate-Free System Shampoo 300ml", 1), ("Matte Texture Clay 85g", 1)], "standard", "cod", [], ""),
    (0, 2, [("Soft-Bristle System Brush", 2)], "pickup", "cod", [], ""),
]


def _demo_vendor():
    return User.objects.filter(role=Role.VENDOR, is_active=True).order_by("pk").first()


def seed_appointments() -> int:
    vendor = _demo_vendor()
    services = {s.name: s for s in Service.objects.all()}
    today = timezone.localdate()
    count = 0
    for offset, at, cust, service_name, status, notes, internal in APPOINTMENTS:
        service = services.get(service_name)
        if service is None:
            continue
        name, phone, email, *_ = CUSTOMERS[cust]
        day = today + timedelta(days=offset)
        requested = timezone.make_aware(datetime.combine(day - timedelta(days=3), datetime.min.time())) + timedelta(
            hours=10 + cust % 8
        )
        appointment = Appointment.objects.create(
            full_name=name,
            phone=phone,
            email=email,
            service=service,
            date=day,
            time=datetime.strptime(at, "%H:%M").time(),
            notes=notes,
            status=status,
            vendor_note=internal,
            handled_by=vendor if status != "pending" else None,
            status_changed_at=requested + timedelta(hours=2) if status != "pending" else None,
        )
        # created_at is auto_now_add; backdate it so lists look realistic.
        Appointment.objects.filter(pk=appointment.pk).update(created_at=requested)
        count += 1
    return count


def seed_orders() -> int:
    vendor = _demo_vendor()
    products = {p.name: p for p in Product.objects.all()}
    count = 0
    for days_ago, cust, lines, shipping, payment, statuses, tracking in ORDERS:
        items = [(products[n], q) for n, q in lines if n in products]
        # Skip lines the demo stock can't cover so stock never goes negative.
        items = [(p, q) for p, q in items if p.show_price and p.stock >= q]
        if not items:
            continue
        name, phone, email, address, city, province = CUSTOMERS[cust]
        subtotal = sum((p.final_price * q for p, q in items), Decimal("0.00"))
        shipping_cost = calculate_shipping(subtotal, shipping)
        order = Order.objects.create(
            full_name=name,
            email=email or f"{name.split()[0].lower()}@example.com",
            phone=phone,
            address_line1="" if shipping == "pickup" else address,
            city="" if shipping == "pickup" else city,
            province="" if shipping == "pickup" else province,
            shipping_method=shipping,
            payment_method=payment,
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            total=subtotal + shipping_cost,
            tracking_number=tracking,
        )
        for product, qty in items:
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                sku=product.sku,
                unit_price=product.final_price,
                quantity=qty,
                line_total=product.final_price * qty,
            )
            adjust_stock(product, -qty, MovementReason.SALE, reference=order.number)
        OrderEvent.objects.create(order=order, status="pending", note="Order placed")

        for status in statuses:
            if status in ("processing", "shipped") and payment == PaymentMethod.BANK_TRANSFER:
                mark_order_paid(order, user=vendor)  # no-op if already paid
            order = change_order_status(order, status, user=vendor)

        # Backdate the order and spread its timeline over the following days.
        placed = timezone.now() - timedelta(days=days_ago, hours=cust)
        number = f"HC{timezone.localtime(placed):%y%m%d}-{order.number.split('-', 1)[1]}"
        StockMovement.objects.filter(reference=order.number).update(reference=number)
        Order.objects.filter(pk=order.pk).update(created_at=placed, number=number)
        for step, event in enumerate(order.events.order_by("pk")):
            OrderEvent.objects.filter(pk=event.pk).update(created_at=placed + timedelta(hours=20 * step))
        count += 1
    return count
