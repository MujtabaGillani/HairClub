"""Reusable, whitelisted sorting and date-range filtering for dashboard list views."""

from datetime import date, timedelta

from django.utils import timezone

DATE_PRESETS = {
    "today": "Today",
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "month": "This month",
    "last_month": "Last month",
}


class SortableListMixin:
    """
    Subclasses define ``sort_options = {"key": ("Label", ["field", ...]), ...}``
    and ``default_sort``. Only whitelisted keys reach ``order_by``, so the
    ``?sort=`` parameter can never inject arbitrary field names.
    """

    sort_options: dict[str, tuple[str, list[str]]] = {}
    default_sort: str = ""

    def get_sort_key(self) -> str:
        key = self.request.GET.get("sort", "")
        return key if key in self.sort_options else self.default_sort

    def apply_sort(self, qs):
        self.sort_key = self.get_sort_key()
        return qs.order_by(*self.sort_options[self.sort_key][1], "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sort"] = getattr(self, "sort_key", self.default_sort)
        context["sort_options"] = {key: label for key, (label, _) in self.sort_options.items()}
        return context


def resolve_date_range(params) -> tuple[date | None, date | None, str]:
    """
    Read ``range`` (a preset) or ``from``/``to`` (YYYY-MM-DD) from query params.
    Returns (start, end, preset_key); invalid input is ignored rather than erroring.
    """
    today = timezone.localdate()
    preset = params.get("range", "")
    if preset == "today":
        return today, today, preset
    if preset == "7d":
        return today - timedelta(days=6), today, preset
    if preset == "30d":
        return today - timedelta(days=29), today, preset
    if preset == "month":
        return today.replace(day=1), today, preset
    if preset == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end, preset

    def parse(value):
        try:
            return date.fromisoformat(value) if value else None
        except ValueError:
            return None

    start, end = parse(params.get("from")), parse(params.get("to"))
    if start and end and start > end:
        start, end = end, start
    return start, end, ""
