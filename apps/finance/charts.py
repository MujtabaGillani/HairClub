"""Server-side geometry for the monthly revenue-vs-costs column chart (rendered as inline SVG)."""

import math
from decimal import Decimal

WIDTH, HEIGHT = 720, 260
PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 64, 8, 12, 28
BAR_MAX = 18  # px, under the 24px cap so each month band keeps some air
BAR_GAP = 2  # surface gap between the two columns of a month
RADIUS = 4


def _nice_step(maximum: float, ticks: int = 4) -> float:
    if maximum <= 0:
        return 1.0
    raw = maximum / ticks
    magnitude = 10 ** math.floor(math.log10(raw))
    for multiple in (1, 2, 2.5, 5, 10):
        if raw <= multiple * magnitude:
            return multiple * magnitude
    return 10 * magnitude


def _column_path(x: float, base: float, top: float, width: float) -> str:
    """Column with a 4px rounded data-end and a square baseline."""
    height = base - top
    if height <= 0:
        return ""
    r = min(RADIUS, height, width / 2)
    return (
        f"M{x:.1f},{base:.1f} V{top + r:.1f} Q{x:.1f},{top:.1f} {x + r:.1f},{top:.1f} "
        f"H{x + width - r:.1f} Q{x + width:.1f},{top:.1f} {x + width:.1f},{top + r:.1f} V{base:.1f} Z"
    )


def compact(value: float) -> str:
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:.0f}"


def revenue_cost_chart(series: list[dict]) -> dict:
    """Columns per month: revenue (series 1) next to total costs = COGS + expenses (series 2)."""
    rows = [{**row, "costs": row["cogs"] + row["expenses"]} for row in series]
    peak = max([float(r["revenue"]) for r in rows] + [float(r["costs"]) for r in rows] + [0.0])
    step = _nice_step(peak)
    top_value = max(step * math.ceil(peak / step), step)

    plot_w = WIDTH - PAD_LEFT - PAD_RIGHT
    plot_h = HEIGHT - PAD_TOP - PAD_BOTTOM
    base = PAD_TOP + plot_h
    band = plot_w / max(len(rows), 1)
    bar = min(BAR_MAX, (band - 10 - BAR_GAP) / 2)

    def y(value) -> float:
        return base - float(value) / top_value * plot_h

    ticks = []
    value = 0.0
    while value <= top_value + 1e-9:
        ticks.append({"y": round(y(value), 1), "label": compact(value)})
        value += step

    months = []
    for i, row in enumerate(rows):
        center = PAD_LEFT + band * i + band / 2
        x_rev = center - BAR_GAP / 2 - bar
        x_cost = center + BAR_GAP / 2
        months.append(
            {
                **row,
                "x": round(center, 1),
                "band_x": round(PAD_LEFT + band * i, 1),
                "band_w": round(band, 1),
                "revenue_path": _column_path(x_rev, base, y(row["revenue"]), bar),
                "costs_path": _column_path(x_cost, base, y(row["costs"]), bar),
            }
        )

    return {
        "width": WIDTH,
        "height": HEIGHT,
        "base": round(base, 1),
        "left": PAD_LEFT,
        "right": WIDTH - PAD_RIGHT,
        "label_y": HEIGHT - 8,
        "ticks": ticks,
        "months": months,
        "has_data": any(r["revenue"] or r["costs"] for r in rows),
        "totals": {
            "revenue": sum((r["revenue"] for r in rows), Decimal("0")),
            "costs": sum((r["costs"] for r in rows), Decimal("0")),
            "net": sum((r["net"] for r in rows), Decimal("0")),
        },
    }
