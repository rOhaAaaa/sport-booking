from django.contrib import admin

from .models import Booking, Payment

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "hall",
        "session",
        "starts_at",
        "ends_at",
        "total_price",
        "status",
    )
    list_filter = ("status",)
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "hall__name",
        "session__section__name",
    )
    list_select_related = (
        "user",
        "hall",
        "session",
        "membership",
    )
    autocomplete_fields = ("user", "hall", "session")
    readonly_fields = ("created_at",)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booking",
        "amount",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = (
        "booking__user__username",
        "booking__user__first_name",
        "booking__user__last_name",
    )
    list_select_related = ("booking", "booking__user")
    autocomplete_fields = ("booking",)
    readonly_fields = ("created_at",)