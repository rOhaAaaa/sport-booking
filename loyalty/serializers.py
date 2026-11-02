from django.db.models import Sum
from rest_framework import serializers

from .models import (
    BonusTransaction,
    LoyaltyCard,
    Membership,
    MembershipPlan,
)


class MembershipPlanSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(
        source="get_kind_display",
        read_only=True,
    )
    service_scope_display = serializers.CharField(
        source="get_service_scope_display",
        read_only=True,
    )
    sport_type_name = serializers.CharField(
        source="sport_type.name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = MembershipPlan
        fields = (
            "id",
            "name",
            "kind",
            "kind_display",
            "price",
            "validity_days",
            "visit_limit",
            "service_scope",
            "service_scope_display",
            "sport_type",
            "sport_type_name",
        )
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    plan = MembershipPlanSerializer(read_only=True)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Membership
        fields = (
            "id",
            "plan",
            "valid_from",
            "valid_until",
            "remaining_visits",
            "status",
            "status_display",
        )
        read_only_fields = fields


class MembershipPurchaseSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(min_value=1)
    payment_successful = serializers.BooleanField()


class LoyaltyCardSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )
    total_points = serializers.SerializerMethodField()

    class Meta:
        model = LoyaltyCard
        fields = (
            "id",
            "category",
            "category_display",
            "total_points",
        )
        read_only_fields = fields

    def get_total_points(self, obj):
        return obj.bonus_transactions.aggregate(
            total=Sum("points", default=0),
        )["total"]


class BonusTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BonusTransaction
        fields = (
            "id",
            "booking",
            "points",
            "created_at",
        )
        read_only_fields = fields