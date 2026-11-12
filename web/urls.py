from django.urls import path

from . import views


app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("halls/", views.halls, name="halls"),
    path("schedule/", views.schedule, name="schedule"),
    path("login/", views.login_page, name="login"),
    path("register/", views.register_page, name="register"),
    path("profile/", views.profile_page, name="profile"),
    path("bookings/", views.bookings_page, name="bookings"),
    path("bookings/<int:booking_id>/confirm/", views.booking_checkout_page, name="booking-checkout"),
    path("loyalty/", views.loyalty_page, name="loyalty"),
]