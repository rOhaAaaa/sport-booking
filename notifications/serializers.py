from rest_framework import serializers

from .models import Notification, Offer


class NotificationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(
        source="get_kind_display",
        read_only=True,
    )

    class Meta:
        model = Notification
        fields = (
            "id",
            "kind",
            "kind_display",
            "message",
            "is_read",
            "created_at",
            "booking",
            "offer",
        )
        read_only_fields = fields


class NotificationFilterSerializer(serializers.Serializer):
    is_read = serializers.BooleanField(required=False)
    kind = serializers.ChoiceField(
        choices=Notification.Kind.choices,
        required=False,
    )


class OfferSerializer(serializers.ModelSerializer):
    target_card_category_display = serializers.CharField(
        source="get_target_card_category_display",
        read_only=True,
    )

    class Meta:
        model = Offer
        fields = (
            "id",
            "title",
            "description",
            "starts_at",
            "ends_at",
            "target_card_category",
            "target_card_category_display",
        )
        read_only_fields = fields