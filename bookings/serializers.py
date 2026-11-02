from rest_framework import serializers

from .models import Booking


class BookingSerializer(serializers.ModelSerializer):
    hall_name = serializers.CharField(
        source="hall.name",
        read_only=True,
        allow_null=True,
    )
    session_name = serializers.CharField(
        source="session.section.name",
        read_only=True,
        allow_null=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Booking
        fields = (
            "id",
            "hall",
            "hall_name",
            "session",
            "session_name",
            "membership",
            "starts_at",
            "ends_at",
            "total_price",
            "status",
            "status_display",
            "created_at",
        )
        read_only_fields = fields


class HallBookingCreateSerializer(serializers.Serializer):
    hall_id = serializers.IntegerField(min_value=1)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()


class SessionBookingCreateSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(min_value=1)