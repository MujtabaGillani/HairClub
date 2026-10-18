from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("track/", views.order_lookup, name="lookup"),
    path("<str:number>/", views.order_detail, name="detail"),
    path("<str:number>/thank-you/", views.order_confirmation, name="confirmation"),
    path("<str:number>/cancel/", views.order_cancel, name="cancel"),
]
