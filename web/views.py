from django.shortcuts import redirect, render
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


@require_GET
def login_page(request):
    if request.user.is_authenticated:
        return redirect("web:home")
    return render(request, "web/auth.html", {"mode": "login"})


@require_GET
def register_page(request):
    if request.user.is_authenticated:
        return redirect("web:home")
    return render(request, "web/auth.html", {"mode": "register"})