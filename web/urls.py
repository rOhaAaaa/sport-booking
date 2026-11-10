from django.urls import path

from . import views


app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("halls/", views.halls, name="halls"),
    path("schedule/", views.schedule, name="schedule"),
    path("login/", views.login_page, name="login"),
    path("register/", views.register_page, name="register"),
]