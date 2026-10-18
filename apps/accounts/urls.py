from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.AccountOverviewView.as_view(), name="overview"),
    path("redirect/", views.login_redirect, name="redirect"),
    path("profile/", views.ProfileUpdateView.as_view(), name="profile"),
    path("orders/", views.MyOrdersView.as_view(), name="orders"),
    path("appointments/", views.MyAppointmentsView.as_view(), name="appointments"),
]
