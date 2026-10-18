"""
Profit & loss reporting.

Revenue recognition (agreed with the business):
* Product sales and shipping charged to the customer count when the order is
  **delivered** (``Order.delivered_at``). Cancelled or undelivered orders never count.
* Service income counts on the date of a **completed** appointment (``amount_charged``).

Cost of goods sold uses the unit cost snapshotted on each order line at checkout,
so editing a product's cost later never rewrites past profit. Stock purchases are
not expenses; they become cost when the stock is sold.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus
from apps.invoices.models import Invoice
from apps.orders.models import Order, OrderItem, OrderStatus

from .models import Expense

ZERO = Decimal("0.00")
MONEY = DecimalField(max_digits=14, decimal_places=2)

PERIOD_CHOICES = {
    "this_month": "This month",
    "last_month": "Last month",
    "this_quarter": "This quarter",
    "this_year": "This year",
    "last_12_months": "Last 12 months",
    "custom": "Custom range",
}


@dataclass(frozen=True)
class Period:
    key: str
    start: date
    end: date  # inclusive

    @property
    def label(self) -> str:
        if self.key != "custom":
            return PERIOD_CHOICES[self.key]
        return f"{self.start:%d %b %Y} – {self.end:%d %b %Y}"

    def bounds(self) -> tuple[datetime, datetime]:
        """Timezone-aware [start, end) datetimes covering the whole of both days."""
        start = timezone.make_aware(datetime.combine(self.start, time.min))
        end = timezone.make_aware(datetime.combine(self.end + timedelta(days=1), time.min))
        return start, end


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    return date(d.year + month_index // 12, month_index % 12 + 1, 1)


def _last_day_of_month(d: date) -> date:
    return _add_months(_month_start(d), 1) - timedelta(days=1)


def previous_period(period: Period) -> tuple[Period, str]:
    """
    The period to compare against, and a short label for it. Month-to-date is
    compared with the same days of last month (not the whole month), so a
    half-finished month isn't judged against a complete one.
    """
    start, end = period.start, period.end
    if period.key == "this_month":
        prev_start = _add_months(start, -1)
        prev_end = min(prev_start + (end - start), _last_day_of_month(prev_start))
        label = f"{prev_start.day}–{prev_end.day} {prev_start:%b}"  # e.g. "1–18 Sep"
    elif period.key == "last_month":
        prev_start = _add_months(start, -1)
        prev_end = start - timedelta(days=1)
        label = f"{prev_start:%B}"
    elif period.key == "this_quarter":
        prev_start = _add_months(start, -3)
        prev_end = min(prev_start + (end - start), _add_months(prev_start, 3) - timedelta(days=1))
        label = "same days last quarter"
    elif period.key == "this_year":
        prev_start = start.replace(year=start.year - 1)
        prev_end = min(prev_start + (end - start), date(prev_start.year, 12, 31))
        label = f"same period {prev_start.year}"
    elif period.key == "last_12_months":
        prev_start = _add_months(start, -12)
        prev_end = start - timedelta(days=1)
        label = "previous 12 months"
    else:
        length = end - start
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - length
        label = "previous period"
    return Period("custom", prev_start, prev_end), label


@dataclass(frozen=True)
class Delta:
    """Change between two amounts. ``higher_is_better`` is False for costs."""

    current: Decimal
    previous: Decimal
    higher_is_better: bool = True

    @property
    def pct(self) -> Decimal | None:
        if not self.previous:
            return None
        return ((self.current - self.previous) / abs(self.previous) * 100).quantize(Decimal("0.1"))

    @property
    def direction(self) -> str:
        if self.current > self.previous:
            return "up"
        if self.current < self.previous:
            return "down"
        return "flat"

    @property
    def is_good(self) -> bool | None:
        if self.direction == "flat":
            return None
        return (self.direction == "up") == self.higher_is_better

    @property
    def pct_abs(self) -> Decimal | None:
        return abs(self.pct) if self.pct is not None else None


def compare_reports(current: "Report", previous: "Report") -> dict[str, Delta]:
    return {
        "revenue": Delta(current.revenue, previous.revenue),
        "gross_profit": Delta(current.gross_profit, previous.gross_profit),
        "expenses": Delta(current.expenses_total, previous.expenses_total, higher_is_better=False),
        "net_profit": Delta(current.net_profit, previous.net_profit),
    }


def resolve_period(key: str | None, start: date | None = None, end: date | None = None) -> Period:
    today = timezone.localdate()
    key = key if key in PERIOD_CHOICES else "this_month"
    if key == "custom" and start and end:
        if start > end:
            start, end = end, start
        return Period("custom", start, end)
    if key == "last_month":
        first = _add_months(_month_start(today), -1)
        return Period(key, first, _month_start(today) - timedelta(days=1))
    if key == "this_quarter":
        first = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        return Period(key, first, today)
    if key == "this_year":
        return Period(key, date(today.year, 1, 1), today)
    if key == "last_12_months":
        return Period(key, _add_months(_month_start(today), -11), today)
    return Period("this_month", _month_start(today), today)


def _sum(qs, expression) -> Decimal:
    return qs.aggregate(total=Coalesce(Sum(expression, output_field=MONEY), Value(ZERO), output_field=MONEY))["total"]


LINE_COST = ExpressionWrapper(F("unit_cost") * F("quantity"), output_field=MONEY)


def _pct(part: Decimal, whole: Decimal) -> Decimal | None:
    if not whole:
        return None
    return (part / whole * 100).quantize(Decimal("0.1"))


@dataclass
class Report:
    period: Period
    product_sales: Decimal = ZERO
    shipping_income: Decimal = ZERO
    service_revenue: Decimal = ZERO
    invoice_revenue: Decimal = ZERO
    invoices_paid: int = 0
    cost_of_goods: Decimal = ZERO
    expenses_total: Decimal = ZERO
    orders_delivered: int = 0
    units_sold: int = 0
    services_completed: int = 0
    lines_missing_cost: int = 0
    pipeline_value: Decimal = ZERO
    pipeline_orders: int = 0
    expenses_by_category: list = field(default_factory=list)
    top_products: list = field(default_factory=list)
    services_breakdown: list = field(default_factory=list)

    @property
    def revenue(self) -> Decimal:
        return self.product_sales + self.shipping_income + self.service_revenue + self.invoice_revenue

    @property
    def gross_profit(self) -> Decimal:
        return self.revenue - self.cost_of_goods

    @property
    def net_profit(self) -> Decimal:
        return self.gross_profit - self.expenses_total

    @property
    def gross_margin(self) -> Decimal | None:
        return _pct(self.gross_profit, self.revenue)

    @property
    def net_margin(self) -> Decimal | None:
        return _pct(self.net_profit, self.revenue)

    @property
    def product_margin(self) -> Decimal | None:
        return _pct(self.product_sales - self.cost_of_goods, self.product_sales)


def build_report(period: Period) -> Report:
    start, end = period.bounds()
    report = Report(period=period)

    delivered = Order.objects.filter(status=OrderStatus.DELIVERED, delivered_at__gte=start, delivered_at__lt=end)
    lines = OrderItem.objects.filter(order__in=delivered)
    report.orders_delivered = delivered.count()
    report.product_sales = _sum(lines, "line_total")
    report.cost_of_goods = _sum(lines, LINE_COST)
    report.shipping_income = _sum(delivered, "shipping_cost")
    report.units_sold = lines.aggregate(n=Coalesce(Sum("quantity"), 0))["n"]
    report.lines_missing_cost = lines.filter(unit_cost=0).count()

    completed = Appointment.objects.filter(
        status=AppointmentStatus.COMPLETED, date__gte=period.start, date__lte=period.end
    )
    report.service_revenue = _sum(completed, "amount_charged")
    report.services_completed = completed.count()
    report.services_breakdown = list(
        completed.values("service__name")
        .annotate(count=Count("id"), revenue=Coalesce(Sum("amount_charged"), Value(ZERO), output_field=MONEY))
        .order_by("-revenue")
    )

    # Standalone invoices (not from an order/appointment) count on their payment date.
    paid_invoices = (
        Invoice.objects.active()
        .standalone()
        .filter(paid_on__gte=period.start, paid_on__lte=period.end, amount_paid__gt=0)
    )
    report.invoice_revenue = _sum(paid_invoices, "amount_paid")
    report.invoices_paid = paid_invoices.count()

    expenses = Expense.objects.filter(date__gte=period.start, date__lte=period.end)
    report.expenses_total = _sum(expenses, "amount")
    report.expenses_by_category = [
        {**row, "share": _pct(row["total"], report.expenses_total)}
        for row in expenses.values("category__name", "category__icon")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    ]

    report.top_products = [
        {**row, "profit": row["revenue"] - row["cost"], "margin": _pct(row["revenue"] - row["cost"], row["revenue"])}
        for row in lines.values("product_name")
        .annotate(units=Sum("quantity"), revenue=Sum("line_total"), cost=Coalesce(Sum(LINE_COST), Value(ZERO)))
        .order_by("-revenue")[:8]
    ]

    open_orders = Order.objects.open()
    report.pipeline_orders = open_orders.count()
    report.pipeline_value = _sum(open_orders, "total")
    return report


def monthly_trend(months: int = 12, end: date | None = None) -> list[dict]:
    """Revenue, costs and net profit per month for the ``months`` months ending with ``end``'s month."""
    end = end or timezone.localdate()
    first = _add_months(_month_start(end), -(months - 1))
    period = Period("custom", first, end)
    start_dt, end_dt = period.bounds()

    def by_month(rows, key="m"):
        return {row[key].date() if isinstance(row[key], datetime) else row[key]: row["v"] for row in rows}

    delivered = OrderItem.objects.filter(
        order__status=OrderStatus.DELIVERED, order__delivered_at__gte=start_dt, order__delivered_at__lt=end_dt
    ).annotate(m=TruncMonth("order__delivered_at"))
    sales = by_month(delivered.values("m").annotate(v=Sum("line_total")))
    cogs = by_month(delivered.values("m").annotate(v=Sum(LINE_COST)))
    shipping = by_month(
        Order.objects.filter(status=OrderStatus.DELIVERED, delivered_at__gte=start_dt, delivered_at__lt=end_dt)
        .annotate(m=TruncMonth("delivered_at"))
        .values("m")
        .annotate(v=Sum("shipping_cost"))
    )
    services = by_month(
        Appointment.objects.filter(status=AppointmentStatus.COMPLETED, date__gte=first, date__lte=end)
        .annotate(m=TruncMonth("date"))
        .values("m")
        .annotate(v=Sum("amount_charged"))
    )
    invoiced = by_month(
        Invoice.objects.active()
        .standalone()
        .filter(paid_on__gte=first, paid_on__lte=end, amount_paid__gt=0)
        .annotate(m=TruncMonth("paid_on"))
        .values("m")
        .annotate(v=Sum("amount_paid"))
    )
    expenses = by_month(
        Expense.objects.filter(date__gte=first, date__lte=end)
        .annotate(m=TruncMonth("date"))
        .values("m")
        .annotate(v=Sum("amount"))
    )

    series = []
    for i in range(months):
        month = _add_months(first, i)
        revenue = sum((source.get(month) or ZERO for source in (sales, shipping, services, invoiced)), ZERO)
        cost = cogs.get(month) or ZERO
        spent = expenses.get(month) or ZERO
        series.append(
            {
                "month": month,
                "label": f"{month:%b %y}",
                "revenue": revenue,
                "cogs": cost,
                "expenses": spent,
                "net": revenue - cost - spent,
            }
        )
    return series
