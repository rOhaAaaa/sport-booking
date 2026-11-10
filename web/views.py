from django.shortcuts import render


def home(request):
    return render(request, "web/catalog.html", {"page": "home"})


def halls(request):
    return render(request, "web/catalog.html", {"page": "halls"})


def schedule(request):
    return render(request, "web/catalog.html", {"page": "schedule"})