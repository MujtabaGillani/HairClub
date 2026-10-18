"""
Data preparation for the monthly revenue / costs / net-profit chart.

The chart itself is drawn client-side (static/js/dashboard.js) at the container's
real pixel width, so text stays crisp and bars keep their thin spec at any size.
"""

from decimal import Decimal

from .services import Delta

MIN_MONTHS = 6


def apply_month_to_date(rows: list[dict], current: dict, previous_same_days: dict, label: str) -> None:
    """
    The latest month is usually only partly over. Comparing it with the whole of
    last month would always look like a drop, so its change badges are recomputed
    against the same days of last month (``previous_same_days``).
    """
    if not rows:
        return
    row = rows[-1]
    row["revenue_delta"] = Delta(current["revenue"], previous_same_days["revenue"])
    row["expenses_delta"] = Delta(current["expenses"], previous_same_days["expenses"], higher_is_better=False)
    row["net_delta"] = Delta(current["net"], previous_same_days["net"])
    row["compare_label"] = label


def trend_chart_data(series: list[dict], min_months: int = MIN_MONTHS) -> dict:
    """
    Trim leading months with no activity (keeping at least ``min_months``) and
    return JSON-safe rows plus totals for the summary strip.
    """
    rows = []
    for i, row in enumerate(series):
        prev = series[i - 1] if i else None
        rows.append(
            {
                **row,
                "costs": row["cogs"] + row["expenses"],
                # Change vs the previous month (None for the first month of the series).
                "revenue_delta": Delta(row["revenue"], prev["revenue"]) if prev else None,
                "expenses_delta": Delta(row["expenses"], prev["expenses"], higher_is_better=False) if prev else None,
                "net_delta": Delta(row["net"], prev["net"]) if prev else None,
            }
        )
    first_active = next((i for i, r in enumerate(rows) if r["revenue"] or r["costs"]), len(rows))
    start = min(first_active, max(len(rows) - min_months, 0))
    rows = rows[start:]

    zero = Decimal("0")
    totals = {
        "revenue": sum((r["revenue"] for r in rows), zero),
        "costs": sum((r["costs"] for r in rows), zero),
        "net": sum((r["net"] for r in rows), zero),
    }
    totals["margin"] = (totals["net"] / totals["revenue"] * 100).quantize(Decimal("0.1")) if totals["revenue"] else None

    return {
        "rows": rows,
        "totals": totals,
        "has_data": any(r["revenue"] or r["costs"] for r in rows),
        "json": [
            {
                "label": f"{r['month']:%b %y}",
                "title": f"{r['month']:%B %Y}",
                "revenue": float(r["revenue"]),
                "cogs": float(r["cogs"]),
                "expenses": float(r["expenses"]),
                "costs": float(r["costs"]),
                "net": float(r["net"]),
                "net_pct": float(r["net_delta"].pct) if r["net_delta"] and r["net_delta"].pct is not None else None,
                "net_good": r["net_delta"].is_good if r["net_delta"] else None,
            }
            for r in rows
        ],
    }
