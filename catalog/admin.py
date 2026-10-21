from django.contrib import admin

from .models import (
    Hall,
    Section,
    SportsCenter,
    SportType,
    Trainer,
    TrainingSession,
)


@admin.register(SportsCenter)
class SportsCenterAdmin(admin.ModelAdmin):
    list_display = ("name", "address")
    search_fields = ("name", "address")


@admin.register(SportType)
class SportTypeAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Hall)
class HallAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "center",
        "sport_type",
        "capacity",
        "hourly_price",
    )
    list_filter = ("center", "sport_type")
    search_fields = ("name", "center__name")
    list_select_related = ("center", "sport_type")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sport_type",
        "skill_level",
        "age_category",
    )
    list_filter = ("sport_type", "skill_level", "age_category")
    search_fields = ("name",)
    list_select_related = ("sport_type",)


@admin.register(Trainer)
class TrainerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "specialization")
    search_fields = ("full_name", "specialization")


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "section",
        "hall",
        "trainer",
        "starts_at",
        "ends_at",
        "capacity",
        "price",
    )
    list_filter = ("section", "hall", "trainer")
    list_select_related = ("section", "hall", "trainer")
    date_hierarchy = "starts_at"