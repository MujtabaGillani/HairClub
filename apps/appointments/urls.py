from django.urls import path

from . import views

app_name = "appointments"

urlpatterns = [
    path("", views.book_appointment, name="book"),
    path("services/", views.ServiceListView.as_view(), name="services"),
    path("slots/", views.available_slots, name="slots"),
    path("booked/<str:reference>/", views.appointment_booked, name="booked"),
]
