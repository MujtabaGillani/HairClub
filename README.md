# HairClub

Website for a non-surgical hair replacement salon. It has four modules:

| Module | What it does |
| --- | --- |
| **Appointments** | Customers choose a treatment, date and an available time slot. The request is saved, then sent to the salon's WhatsApp with every detail pre-filled. Vendors confirm, complete or cancel it from the dashboard and can message the client back on WhatsApp in one click. |
| **Shop** | Hair patches and products: catalogue with search, filters and sorting; product gallery (up to 7 images); favourites; session cart; checkout as a guest or signed in (email/password or Google); cash on delivery or bank transfer; order tracking. |
| **Accounts** | Two roles. **Customers** sign up publicly. **Vendors** (salon staff) are created by an admin only. |
| **Vendor dashboard** | Products (create/edit/delete, 1–7 images, discount, show/hide price, publish, feature) · Inventory (stock levels, low-stock alerts, audited adjustments, stock history) · Appointments (confirm/complete/cancel/no-show) · Orders · Services · Store settings. |

Stack: Django 5.2 LTS · Python 3.12 · django-allauth (Google sign-in) · Bootstrap 5.3 · vanilla JS · SQLite (dev) / PostgreSQL (prod).

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
python manage.py migrate
python manage.py seed_demo        # demo categories, services and products
python manage.py createvendor --email you@example.com --first-name Ayesha
python manage.py createsuperuser  # optional: Django admin at /admin/
python manage.py runserver
```

* Storefront: http://localhost:8000/
* Vendor dashboard: http://localhost:8000/dashboard/ (sign in with the vendor account)

### Google sign-in

1. In Google Cloud Console → *APIs & Services → Credentials*, create an **OAuth client ID** (Web application).
2. Add the authorised redirect URI `http://localhost:8000/accounts/google/login/callback/` (and your production domain's equivalent).
3. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`. The "Continue with Google" button appears automatically once both are set.

### WhatsApp number, opening hours, shipping fees

These live in **Dashboard → Store settings**, so the salon can change them without a deployment. The WhatsApp number must be in international format, digits only (e.g. `923001234567`).

---

## Project layout

```
HairClub/settings/   base.py · dev.py · prod.py · test.py   (env-driven, see .env.example)
apps/
  core/          SiteSettings singleton, WhatsApp link builder, template tags, form renderer, seed_demo
  accounts/      Custom User (role = customer | vendor), vendor permission mixin, createvendor
  catalog/       Category, Product, ProductImage, image validation, shop views
  inventory/     StockMovement ledger + adjust_stock() service (single entry point for stock changes)
  cart/          Session cart service (works for guests)
  wishlist/      Favourites (signed-in users)
  orders/        Order, OrderItem (price snapshot), OrderEvent (audit trail), checkout & status services
  appointments/  Service, Appointment, slot engine, booking & WhatsApp message services
  dashboard/     Vendor-only views and forms (no models of its own)
templates/       Site, account, allauth overrides, dashboard
static/          css/main.css (design system) · css/dashboard.css · js/main.js · js/dashboard.js
```

### Design decisions

* **Business logic lives in `services.py`, not views.** Examples: `place_order`, `change_order_status`, `adjust_stock`, `create_appointment`, `get_slots`. Views stay thin, and the rules are unit-tested directly.
* **Stock is always consistent.** Every change goes through `inventory.services.adjust_stock`, which locks the product row (`select_for_update`), refuses to go negative and writes a `StockMovement` entry. Checkout locks all cart products in primary-key order, re-reads prices from the database and runs in one transaction. Cancelling an order returns its stock automatically.
* **The cart can't be tampered with.** The session stores only product IDs and quantities. Prices, availability and stock limits are re-checked on every read.
* **Order history survives product changes.** `OrderItem` keeps a snapshot of the name, SKU and price, so editing or deleting a product never alters past orders.
* **Status workflows are explicit.** Orders and appointments have allowed-transition maps. Illegal moves (e.g. *pending → delivered*) are rejected. Every order status change is recorded in `OrderEvent`.
* **Appointment slots are concurrency-safe.** Slots come from opening hours, interval, closed days, minimum notice and per-slot capacity. Booking re-checks availability under a lock, so two clients can't take the last place in the same slot.
* **Access control:** `VendorRequiredMixin`. Anonymous users are sent to sign-in and customers get HTTP 403. Every state-changing action is POST + CSRF. Guests can see only orders placed or looked up (number + email) in their own browser session. `next` redirects are validated to stop open redirects.
* **Uploads are validated.** Images must really be JPEG/PNG/WebP (checked with Pillow, not by file extension), at most 5 MB each, and 1–7 per product (`PRODUCT_MIN_IMAGES` / `PRODUCT_MAX_IMAGES`). Files are deleted from storage when their image record is removed.
* **The front end works without JavaScript.** JS adds AJAX add-to-cart and favourites, live time slots, live checkout totals and the image manager, but every form also works as a normal post.

---

## Quality checks

```bash
python manage.py test apps                                  # 96 tests
ruff check . && ruff format --check .                       # lint + formatting
coverage run manage.py test apps && coverage report         # coverage
DJANGO_SECRET_KEY=... python manage.py check --deploy --settings=HairClub.settings.prod
```

Tests cover pricing and discounts, image validation, the cart (stock clamping, hidden-price items, tampered sessions, open redirects), checkout (guest and signed-in, stock decrement, price changes, sold-out items, shipping rules, cancellation and restock, guest order privacy), appointments (slot engine, closed days, capacity, the WhatsApp message, privacy) and dashboard access control and CRUD for all vendor features.

---

## Production deployment

1. Set `DJANGO_SETTINGS_MODULE=HairClub.settings.prod` (the default in `wsgi.py`/`asgi.py`). Also set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, the `DB_*` PostgreSQL variables and SMTP `EMAIL_*`.
2. `pip install -r requirements.txt gunicorn psycopg[binary]`
3. `python manage.py migrate && python manage.py collectstatic --noinput`
4. Run `gunicorn HairClub.wsgi` behind Nginx (or a PaaS) with HTTPS. WhiteNoise serves static files. Serve `/media/` from Nginx or object storage.
5. In the Django admin, set **Sites → domain** to your real domain (used in emails and OAuth).

Production settings enable HTTPS redirect, HSTS, secure cookies, `X-Frame-Options: DENY` and a strict referrer policy.

---

## Content to replace before launch

The demo data (`seed_demo`), bank details, address and phone numbers are placeholders. Update them in **Store settings**, replace the generated product images with real photos, and review the copy on the Home and About pages.
