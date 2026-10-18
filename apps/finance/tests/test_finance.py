from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus
from apps.appointments.services import InvalidTransition as AppointmentTransitionError
from apps.appointments.services import change_appointment_status
from apps.core.testing import make_product, make_service, make_user, make_vendor
from apps.finance.charts import trend_chart_data
from apps.finance.models import Expense, ExpenseCategory
from apps.finance.services import Period, build_report, monthly_trend, resolve_period
from apps.orders.models import Order, OrderItem, OrderStatus
from apps.orders.services import change_order_status

D = Decimal


def make_order(*, status=OrderStatus.PENDING, delivered_at=None, lines=None, shipping=None):
    lines = lines or ((D("1000"), D("400"), 2),)
    shipping = D("250") if shipping is None else shipping
    subtotal = sum((price * qty for price, _, qty in lines), D("0"))
    order = Order.objects.create(
        full_name="A",
        email="a@example.com",
        phone="0300",
        subtotal=subtotal,
        shipping_cost=shipping,
        total=subtotal + shipping,
        status=status,
        delivered_at=delivered_at,
    )
    for price, cost, qty in lines:
        OrderItem.objects.create(
            order=order,
            product_name="Item",
            sku="X",
            unit_price=price,
            quantity=qty,
            line_total=price * qty,
            unit_cost=cost,
        )
    return order


def this_month() -> Period:
    return resolve_period("this_month")


class ProductCostTests(TestCase):
    def test_unit_cost_profit_and_margin(self):
        product = make_product(
            price=D("2000"),
            discount_percent=10,
            purchase_cost=D("900"),
            inbound_shipping_cost=D("150"),
            other_cost=D("30"),
        )
        self.assertEqual(product.unit_cost, D("1080.00"))
        self.assertEqual(product.unit_profit, D("720.00"))  # 1800 - 1080
        self.assertEqual(product.margin_percent, D("40.0"))
        self.assertTrue(product.has_cost)

    def test_no_cost_means_full_margin_flagged(self):
        product = make_product(price=D("500"))
        self.assertFalse(product.has_cost)
        self.assertEqual(product.margin_percent, D("100.0"))


class CostSnapshotTests(TestCase):
    def test_checkout_snapshots_cost_and_later_changes_do_not_rewrite_it(self):
        product = make_product(price=D("1000"), purchase_cost=D("300"), other_cost=D("50"), stock=5)
        self.client.post(reverse("cart:add", args=[product.pk]), {"quantity": 2})
        self.client.post(
            reverse("orders:checkout"),
            {
                "full_name": "Ali",
                "email": "ali@example.com",
                "phone": "03001234567",
                "shipping_method": "pickup",
                "payment_method": "cod",
            },
        )
        item = OrderItem.objects.get()
        self.assertEqual(item.unit_cost, D("350.00"))
        product.purchase_cost = D("900")
        product.save()
        item.refresh_from_db()
        self.assertEqual(item.line_cost, D("700.00"))
        self.assertEqual(item.order.gross_profit, D("1300.00"))

    def test_delivering_sets_delivered_at(self):
        order = make_order(status=OrderStatus.SHIPPED)
        order = change_order_status(order, OrderStatus.DELIVERED)
        self.assertIsNotNone(order.delivered_at)


class ReportTests(TestCase):
    def setUp(self):
        self.rent = ExpenseCategory.objects.get(name="Rent")
        self.food = ExpenseCategory.objects.get(name="Food & refreshments")
        self.now = timezone.now()

    def test_profit_and_loss_figures(self):
        # Counted: delivered this period. 2 x 1000 sold, cost 400 each, shipping 250.
        make_order(status=OrderStatus.DELIVERED, delivered_at=self.now)
        # Not counted: pending, cancelled, delivered long ago.
        make_order(status=OrderStatus.PENDING)
        make_order(status=OrderStatus.CANCELLED)
        make_order(status=OrderStatus.DELIVERED, delivered_at=self.now - timedelta(days=400))
        # Services: one completed today (counted), one confirmed (not).
        service = make_service(starting_price=D("5000"))
        today = timezone.localdate()
        Appointment.objects.create(
            full_name="S",
            phone="0300",
            service=service,
            date=today,
            time=time(12),
            status=AppointmentStatus.COMPLETED,
            amount_charged=D("4500"),
        )
        Appointment.objects.create(
            full_name="S",
            phone="0300",
            service=service,
            date=today,
            time=time(13),
            status=AppointmentStatus.CONFIRMED,
        )
        Expense.objects.create(date=today, category=self.rent, amount=D("3000"), description="Rent")
        Expense.objects.create(date=today, category=self.food, amount=D("500"), description="Lunch")
        Expense.objects.create(
            date=today - timedelta(days=400), category=self.rent, amount=D("9999"), description="Old"
        )

        r = build_report(this_month())
        self.assertEqual(r.product_sales, D("2000"))
        self.assertEqual(r.shipping_income, D("250"))
        self.assertEqual(r.service_revenue, D("4500"))
        self.assertEqual(r.revenue, D("6750"))
        self.assertEqual(r.cost_of_goods, D("800"))
        self.assertEqual(r.gross_profit, D("5950"))
        self.assertEqual(r.expenses_total, D("3500"))
        self.assertEqual(r.net_profit, D("2450"))
        self.assertEqual(r.net_margin, D("36.3"))
        self.assertEqual((r.orders_delivered, r.units_sold, r.services_completed), (1, 2, 1))
        self.assertEqual([row["category__name"] for row in r.expenses_by_category], ["Rent", "Food & refreshments"])
        self.assertEqual(r.pipeline_orders, 1)  # only the pending one is still open
        self.assertEqual(r.top_products[0]["profit"], D("1200"))

    def test_missing_costs_are_flagged(self):
        make_order(status=OrderStatus.DELIVERED, delivered_at=self.now, lines=((D("1000"), D("0"), 1),))
        self.assertEqual(build_report(this_month()).lines_missing_cost, 1)

    def test_empty_period_has_no_margins(self):
        r = build_report(this_month())
        self.assertEqual(r.revenue, D("0"))
        self.assertIsNone(r.net_margin)

    def test_periods(self):
        today = timezone.localdate()
        self.assertEqual(resolve_period("this_month").start, today.replace(day=1))
        last = resolve_period("last_month")
        self.assertEqual(last.end, today.replace(day=1) - timedelta(days=1))
        self.assertEqual(last.start.day, 1)
        custom = resolve_period("custom", date(2026, 3, 31), date(2026, 3, 1))
        self.assertEqual((custom.start, custom.end), (date(2026, 3, 1), date(2026, 3, 31)))  # swapped
        self.assertEqual(resolve_period("bogus").key, "this_month")

    def test_monthly_trend_and_chart(self):
        make_order(status=OrderStatus.DELIVERED, delivered_at=self.now)
        Expense.objects.create(date=timezone.localdate(), category=self.rent, amount=D("1000"), description="R")
        trend = monthly_trend(3)
        self.assertEqual(len(trend), 3)
        self.assertEqual(trend[-1]["revenue"], D("2250"))
        self.assertEqual(trend[-1]["net"], D("2250") - D("800") - D("1000"))
        chart = trend_chart_data(trend, min_months=2)
        self.assertTrue(chart["has_data"])
        self.assertEqual(len(chart["rows"]), 2)  # leading empty month trimmed, minimum kept
        self.assertEqual(chart["json"][-1]["net"], 450.0)
        self.assertEqual(chart["totals"]["revenue"], D("2250"))

    def test_chart_trims_only_leading_empty_months(self):
        empty = {"revenue": D("0"), "cogs": D("0"), "expenses": D("0"), "net": D("0")}
        busy = {"revenue": D("100"), "cogs": D("10"), "expenses": D("0"), "net": D("90")}
        months = [date(2026, m, 1) for m in range(1, 11)]
        series = [{**(busy if m.month in (5, 8) else empty), "month": m} for m in months]
        chart = trend_chart_data(series, min_months=3)
        self.assertEqual([r["month"].month for r in chart["rows"]], [5, 6, 7, 8, 9, 10])  # gap months kept
        quiet = trend_chart_data([{**empty, "month": m} for m in months], min_months=3)
        self.assertEqual(len(quiet["rows"]), 3)
        self.assertFalse(quiet["has_data"])


class AppointmentIncomeTests(TestCase):
    def test_completing_requires_amount(self):
        appt = Appointment.objects.create(
            full_name="S",
            phone="0300",
            service=make_service(),
            date=timezone.localdate(),
            time=time(12),
            status=AppointmentStatus.CONFIRMED,
        )
        with self.assertRaises(AppointmentTransitionError):
            change_appointment_status(appt, AppointmentStatus.COMPLETED)
        appt = change_appointment_status(appt, AppointmentStatus.COMPLETED, amount_charged=D("0"))
        self.assertEqual(appt.amount_charged, D("0"))

    def test_dashboard_completion_records_amount(self):
        vendor = make_vendor()
        self.client.force_login(vendor)
        appt = Appointment.objects.create(
            full_name="S",
            phone="0300",
            service=make_service(),
            date=timezone.localdate(),
            time=time(12),
            status=AppointmentStatus.CONFIRMED,
        )
        url = reverse("dashboard:appointment_status", args=[appt.reference])
        self.client.post(url, {"status": "completed"})
        appt.refresh_from_db()
        self.assertEqual(appt.status, AppointmentStatus.CONFIRMED, "missing amount must block completion")
        self.client.post(url, {"status": "completed", "amount_charged": "6500"})
        appt.refresh_from_db()
        self.assertEqual((appt.status, appt.amount_charged), (AppointmentStatus.COMPLETED, D("6500")))


class FinanceDashboardTests(TestCase):
    def test_access_control(self):
        urls = [reverse("dashboard:finance"), reverse("dashboard:expense_list"), reverse("dashboard:expense_create")]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(make_user())
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_overview_renders_for_each_period(self):
        self.client.force_login(make_vendor())
        make_order(status=OrderStatus.DELIVERED, delivered_at=timezone.now())
        for params in (
            {},
            {"period": "last_12_months"},
            {"period": "custom", "start": "2026-01-01", "end": "2026-12-31"},
        ):
            response = self.client.get(reverse("dashboard:finance"), params)
            self.assertEqual(response.status_code, 200, params)
            self.assertIn("report", response.context)

    def test_expense_crud(self):
        vendor = make_vendor()
        self.client.force_login(vendor)
        rent = ExpenseCategory.objects.get(name="Rent")
        response = self.client.post(
            reverse("dashboard:expense_create"),
            {
                "date": "2026-10-05",
                "category": rent.pk,
                "amount": "60000",
                "description": "October rent",
                "paid_to": "Landlord",
                "payment_method": "bank",
            },
        )
        self.assertRedirects(response, reverse("dashboard:expense_list"))
        expense = Expense.objects.get()
        self.assertEqual((expense.amount, expense.created_by), (D("60000"), vendor))

        self.client.post(
            reverse("dashboard:expense_update", args=[expense.pk]),
            {
                "date": "2026-10-05",
                "category": rent.pk,
                "amount": "65000",
                "description": "October rent",
                "payment_method": "bank",
            },
        )
        expense.refresh_from_db()
        self.assertEqual(expense.amount, D("65000"))

        listing = self.client.get(reverse("dashboard:expense_list"), {"month": "2026-10", "category": rent.pk})
        self.assertEqual(listing.context["filtered_total"], D("65000"))

        self.client.post(reverse("dashboard:expense_delete", args=[expense.pk]))
        self.assertFalse(Expense.objects.exists())

    def test_expense_amount_must_be_positive(self):
        self.client.force_login(make_vendor())
        response = self.client.post(
            reverse("dashboard:expense_create"),
            {
                "date": "2026-10-05",
                "category": ExpenseCategory.objects.first().pk,
                "amount": "0",
                "description": "x",
                "payment_method": "cash",
            },
        )
        self.assertIn("amount", response.context["form"].errors)


class ComparisonTests(TestCase):
    def test_previous_periods(self):
        from apps.finance.services import previous_period

        month_to_date = Period("this_month", date(2026, 10, 1), date(2026, 10, 18))
        prev, label = previous_period(month_to_date)
        self.assertEqual((prev.start, prev.end), (date(2026, 9, 1), date(2026, 9, 18)))
        self.assertIn("Sep", label)
        # Month-to-date on the 31st compares against a 30-day month without overflowing.
        prev, _ = previous_period(Period("this_month", date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(prev.end, date(2026, 9, 30))
        prev, label = previous_period(Period("last_month", date(2026, 9, 1), date(2026, 9, 30)))
        self.assertEqual((prev.start, prev.end, label), (date(2026, 8, 1), date(2026, 8, 31), "August"))
        prev, _ = previous_period(Period("custom", date(2026, 3, 10), date(2026, 3, 19)))
        self.assertEqual((prev.start, prev.end), (date(2026, 2, 28), date(2026, 3, 9)))

    def test_delta_direction_and_colour(self):
        from apps.finance.services import Delta

        up = Delta(D("150"), D("100"))
        self.assertEqual((up.pct, up.direction, up.is_good), (D("50.0"), "up", True))
        costs_up = Delta(D("150"), D("100"), higher_is_better=False)
        self.assertFalse(costs_up.is_good)  # rising costs are bad -> red
        down = Delta(D("80"), D("100"))
        self.assertEqual((down.pct_abs, down.is_good), (D("20.0"), False))
        loss_to_profit = Delta(D("50"), D("-100"))
        self.assertEqual((loss_to_profit.pct, loss_to_profit.is_good), (D("150.0"), True))
        self.assertIsNone(Delta(D("10"), D("0")).pct)  # shown as "New"
        self.assertIsNone(Delta(D("5"), D("5")).is_good)

    def test_monthly_rows_carry_changes_and_page_renders_badges(self):
        today = timezone.localdate()
        rent = ExpenseCategory.objects.get(name="Rent")
        Expense.objects.create(date=today, category=rent, amount=D("1000"), description="Now")
        last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=10)
        Expense.objects.create(date=last_month, category=rent, amount=D("500"), description="Before")
        chart = trend_chart_data(monthly_trend(3), min_months=2)
        self.assertEqual(chart["rows"][-1]["expenses_delta"].pct, D("100.0"))
        self.assertFalse(chart["rows"][-1]["expenses_delta"].is_good)

        self.client.force_login(make_vendor())
        response = self.client.get(reverse("dashboard:finance"), {"period": "last_12_months"})
        self.assertContains(response, "Month by month")
        self.assertContains(response, 'class="delta is-bad"')
        self.assertIn("deltas", response.context)
