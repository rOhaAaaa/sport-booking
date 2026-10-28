from django.contrib import admin

from .models import (
    BonusTransaction,
    LoyaltyCard,
    Membership,
    MembershipPlan,
)

@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "kind",
        "price",
        "validity_days",
        "visit_limit",
        "service_scope",
        "sport_type",
    )
    list_filter = (
        "kind",
        "service_scope",
        "sport_type",
    )
    search_fields = ("name",)
    list_select_related = ("sport_type",)


@admin.register(LoyaltyCard)
class LoyaltyCardAdmin(admin.ModelAdmin):
    list_display = ("user", "category")
    list_filter = ("category",)
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )
    list_select_related = ("user",)
    autocomplete_fields = ("user",)

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "plan",
        "valid_from",
        "valid_until",
        "remaining_visits",
        "status",
    )
    list_filter = (
        "status",
        "plan__kind",
    )
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "plan__name",
    )
    list_select_related = ("user", "plan")
    autocomplete_fields = ("user", "plan")

@admin.register(BonusTransaction)
class BonusTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "card",
        "booking",
        "points",
        "created_at",
    )
    search_fields = (
        "card__user__username",
        "card__user__first_name",
        "card__user__last_name",
    )
    list_select_related = (
        "card",
        "card__user",
        "booking",
    )
    autocomplete_fields = ("booking",)
    readonly_fields = ("created_at",)