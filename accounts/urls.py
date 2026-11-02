from django.urls import path

from .views import (
    CSRFTokenView,
    LoginView,
    LogoutView,
    OwnProfileView,
    RegistrationView,
)


app_name = "accounts"

urlpatterns = [
    path("csrf/", CSRFTokenView.as_view(), name="csrf"),
    path(
        "register/",
        RegistrationView.as_view(),
        name="register",
    ),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", OwnProfileView.as_view(), name="profile"),
]