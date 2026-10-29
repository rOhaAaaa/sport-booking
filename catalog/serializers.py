from rest_framework import serializers

from .models import (
    Hall,
    Section,
    SportsCenter,
    SportType,
    Trainer,
    TrainingSession,
)


class SportsCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SportsCenter
        fields = ("id", "name", "address")
        read_only_fields = fields


class SportTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SportType
        fields = ("id", "name")
        read_only_fields = fields


class HallSerializer(serializers.ModelSerializer):
    center_name = serializers.CharField(
        source="center.name",
        read_only=True,
    )
    sport_type_name = serializers.CharField(
        source="sport_type.name",
        read_only=True,
    )

    class Meta:
        model = Hall
        fields = (
            "id",
            "name",
            "center",
            "center_name",
            "sport_type",
            "sport_type_name",
            "capacity",
            "hourly_price",
        )
        read_only_fields = fields


class SectionSerializer(serializers.ModelSerializer):
    sport_type_name = serializers.CharField(
        source="sport_type.name",
        read_only=True,
    )
    skill_level_display = serializers.CharField(
        source="get_skill_level_display",
        read_only=True,
    )
    age_category_display = serializers.CharField(
        source="get_age_category_display",
        read_only=True,
    )

    class Meta:
        model = Section
        fields = (
            "id",
            "name",
            "sport_type",
            "sport_type_name",
            "skill_level",
            "skill_level_display",
            "age_category",
            "age_category_display",
        )
        read_only_fields = fields


class TrainerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trainer
        fields = ("id", "full_name", "specialization")
        read_only_fields = fields


class TrainingSessionSerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(
        source="section.name",
        read_only=True,
    )
    hall_name = serializers.CharField(
        source="hall.name",
        read_only=True,
    )
    trainer_name = serializers.CharField(
        source="trainer.full_name",
        read_only=True,
    )
    sport_type = serializers.IntegerField(
        source="section.sport_type_id",
        read_only=True,
    )
    sport_type_name = serializers.CharField(
        source="section.sport_type.name",
        read_only=True,
    )

    class Meta:
        model = TrainingSession
        fields = (
            "id",
            "section",
            "section_name",
            "hall",
            "hall_name",
            "trainer",
            "trainer_name",
            "sport_type",
            "sport_type_name",
            "starts_at",
            "ends_at",
            "capacity",
            "price",
        )
        read_only_fields = fields