from django.contrib import admin

from .models import Notification, Offer


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "target_card_category",
        "starts_at",
        "ends_at",
    )
    list_filter = ("target_card_category",)
    search_fields = ("title", "description")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "kind",
        "is_read",
        "created_at",
    )
    list_filter = ("kind", "is_read")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "message",
    )
    list_select_related = (
        "user",
        "booking",
        "offer",
    )
    autocomplete_fields = (
        "user",
        "booking",
        "offer",
    )
    readonly_fields = ("created_at",)