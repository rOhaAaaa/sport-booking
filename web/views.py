from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
def home(request):
    return render(request, "web/catalog.html", {"page": "home"})


@require_GET
def halls(request):
    return render(request, "web/catalog.html", {"page": "halls"})


@require_GET
def schedule(request):
    return render(request, "web/catalog.html", {"page": "schedule"})


@never_cache
@require_GET
def login_page(request):
    if request.user.is_authenticated:
        return redirect("web:home")
    return render(request, "web/auth.html", {"mode": "login"})


@never_cache
@require_GET
def register_page(request):
    if request.user.is_authenticated:
        return redirect("web:home")
    return render(request, "web/auth.html", {"mode": "register"})


@never_cache
@login_required(login_url="web:login")
@require_GET
def profile_page(request):
    return render(request, "web/profile.html")


@never_cache
@login_required(login_url="web:login")
@require_GET
def bookings_page(request):
    return render(request, "web/bookings.html")