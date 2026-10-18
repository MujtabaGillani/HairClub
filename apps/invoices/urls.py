from django.urls import path

from . import views

app_name = "invoices"

urlpatterns = [
    path("<str:token>/", views.public_invoice, name="public"),
    path("<str:token>/pdf/", views.public_invoice_pdf, name="public_pdf"),
]
