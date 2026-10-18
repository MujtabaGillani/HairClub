from django.urls import path

from .views import appointments, finance, inventory, invoices, orders, overview, products, services, settings

app_name = "dashboard"

urlpatterns = [
    path("", overview.OverviewView.as_view(), name="overview"),
    # Products
    path("products/", products.ProductListView.as_view(), name="product_list"),
    path("products/new/", products.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/edit/", products.ProductUpdateView.as_view(), name="product_update"),
    path("products/<int:pk>/delete/", products.ProductDeleteView.as_view(), name="product_delete"),
    path("products/<int:pk>/toggle/<str:field>/", products.ProductToggleView.as_view(), name="product_toggle"),
    # Inventory
    path("inventory/", inventory.InventoryListView.as_view(), name="inventory"),
    path("inventory/history/", inventory.StockHistoryView.as_view(), name="stock_history"),
    path("inventory/<int:pk>/adjust/", inventory.StockAdjustView.as_view(), name="stock_adjust"),
    path("inventory/<int:pk>/history/", inventory.StockHistoryView.as_view(), name="product_stock_history"),
    # Appointments
    path("appointments/", appointments.AppointmentListView.as_view(), name="appointment_list"),
    path("appointments/<str:reference>/", appointments.AppointmentDetailView.as_view(), name="appointment_detail"),
    path(
        "appointments/<str:reference>/status/",
        appointments.AppointmentStatusView.as_view(),
        name="appointment_status",
    ),
    # Orders
    path("orders/", orders.OrderListView.as_view(), name="order_list"),
    path("orders/<str:number>/", orders.OrderDetailView.as_view(), name="order_detail"),
    path("orders/<str:number>/status/", orders.OrderStatusView.as_view(), name="order_status"),
    path("orders/<str:number>/mark-paid/", orders.OrderMarkPaidView.as_view(), name="order_mark_paid"),
    # Invoices
    path("invoices/", invoices.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/new/", invoices.InvoiceEditorView.as_view(), name="invoice_create"),
    path("invoices/<int:pk>/", invoices.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/edit/", invoices.InvoiceEditorView.as_view(), name="invoice_update"),
    path("invoices/<int:pk>/pdf/", invoices.InvoicePdfView.as_view(), name="invoice_pdf"),
    path("invoices/<int:pk>/<slug:action>/", invoices.InvoiceActionView.as_view(), name="invoice_action"),
    # Finance
    path("finance/", finance.FinanceOverviewView.as_view(), name="finance"),
    path("finance/expenses/", finance.ExpenseListView.as_view(), name="expense_list"),
    path("finance/expenses/new/", finance.ExpenseCreateView.as_view(), name="expense_create"),
    path("finance/expenses/<int:pk>/edit/", finance.ExpenseUpdateView.as_view(), name="expense_update"),
    path("finance/expenses/<int:pk>/delete/", finance.ExpenseDeleteView.as_view(), name="expense_delete"),
    # Services & settings
    path("services/", services.ServiceListView.as_view(), name="service_list"),
    path("services/new/", services.ServiceCreateView.as_view(), name="service_create"),
    path("services/<int:pk>/edit/", services.ServiceUpdateView.as_view(), name="service_update"),
    path("settings/", settings.SiteSettingsView.as_view(), name="settings"),
]
