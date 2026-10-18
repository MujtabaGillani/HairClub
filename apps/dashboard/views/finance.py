from django.contrib import messages
from django.db.models import Q, Sum
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from apps.accounts.permissions import VendorRequiredMixin
from apps.finance.charts import revenue_cost_chart
from apps.finance.models import Expense
from apps.finance.services import PERIOD_CHOICES, build_report, monthly_trend, resolve_period

from ..forms import ExpenseFilterForm, ExpenseForm, FinancePeriodForm


class FinanceOverviewView(VendorRequiredMixin, TemplateView):
    template_name = "dashboard/finance/overview.html"

    def get_context_data(self, **kwargs):
        form = FinancePeriodForm(self.request.GET or None)
        data = form.cleaned_data if form.is_valid() else {}
        period = resolve_period(data.get("period"), data.get("start"), data.get("end"))
        trend = monthly_trend(12, end=period.end)
        return super().get_context_data(
            nav="finance",
            form=form,
            period=period,
            period_choices=PERIOD_CHOICES,
            report=build_report(period),
            trend=trend,
            chart=revenue_cost_chart(trend),
            **kwargs,
        )


class ExpenseListView(VendorRequiredMixin, ListView):
    template_name = "dashboard/finance/expense_list.html"
    context_object_name = "expenses"
    paginate_by = 25

    def get_queryset(self):
        self.filter_form = ExpenseFilterForm(self.request.GET or None)
        qs = Expense.objects.select_related("category", "created_by")
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if month := data.get("month"):
                qs = qs.filter(date__year=month.year, date__month=month.month)
            if data.get("category"):
                qs = qs.filter(category=data["category"])
            if term := (data.get("q") or "").strip():
                qs = qs.filter(Q(description__icontains=term) | Q(paid_to__icontains=term) | Q(notes__icontains=term))
        return qs

    def get_context_data(self, **kwargs):
        qs = self.object_list
        return super().get_context_data(
            nav="expenses",
            filter_form=self.filter_form,
            filtered_total=qs.aggregate(total=Sum("amount"))["total"] or 0,
            by_category=qs.values("category__name").annotate(total=Sum("amount")).order_by("-total")[:6],
            **kwargs,
        )


class ExpenseFormMixin(VendorRequiredMixin):
    model = Expense
    form_class = ExpenseForm
    template_name = "dashboard/finance/expense_form.html"
    success_url = reverse_lazy("dashboard:expense_list")
    extra_context = {"nav": "expenses"}

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.created_by = self.request.user
        messages.success(self.request, f"Expense “{form.instance.description}” saved.")
        return super().form_valid(form)

    def get_success_url(self):
        if "save_and_add" in self.request.POST:
            return reverse_lazy("dashboard:expense_create")
        return super().get_success_url()


class ExpenseCreateView(ExpenseFormMixin, CreateView):
    pass


class ExpenseUpdateView(ExpenseFormMixin, UpdateView):
    pass


class ExpenseDeleteView(VendorRequiredMixin, DeleteView):
    model = Expense
    template_name = "dashboard/finance/expense_confirm_delete.html"
    success_url = reverse_lazy("dashboard:expense_list")
    context_object_name = "expense"
    extra_context = {"nav": "expenses"}

    def form_valid(self, form):
        messages.success(self.request, f"Expense “{self.object.description}” deleted.")
        return super().form_valid(form)
