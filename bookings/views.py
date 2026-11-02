from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Booking
from .serializers import (
    BookingSerializer,
    HallBookingCreateSerializer,
    SessionBookingCreateSerializer,
    BookingConfirmationSerializer,
)
from .services import BookingCheckoutService, BookingService


class BookingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = BookingSerializer
    filter_backends = []
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            Booking.objects.filter(user=self.request.user)
            .select_related(
                "hall",
                "session__section",
                "membership",
            )
            .order_by("-created_at", "-pk")
        )

    def get_serializer_class(self):
        if self.action == "create_hall":
            return HallBookingCreateSerializer
        if self.action == "create_session":
            return SessionBookingCreateSerializer
        if self.action == "confirm":
            return BookingConfirmationSerializer
        return BookingSerializer

    def booking_response(self, booking):
        serializer = BookingSerializer(
            booking,
            context=self.get_serializer_context(),
        )
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )

    def raise_service_error(self, error):
        if hasattr(error, "message_dict"):
            detail = error.message_dict
        else:
            detail = {"non_field_errors": error.messages}

        raise serializers.ValidationError(detail) from error

    @action(
        detail=False,
        methods=["post"],
        url_path="hall",
        url_name="create-hall",
    )
    def create_hall(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            booking = BookingService.create_hall_booking(
                user=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as error:
            self.raise_service_error(error)

        return self.booking_response(booking)

    @action(
        detail=False,
        methods=["post"],
        url_path="session",
        url_name="create-session",
    )
    def create_session(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            booking = BookingService.create_session_booking(
                user=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as error:
            self.raise_service_error(error)

        return self.booking_response(booking)

    @action(
    detail=True,
    methods=["post"],
    url_path="confirm",
    url_name="confirm",
)
    def confirm(self, request, pk=None):
        booking = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            booking = BookingCheckoutService.confirm(
                user=request.user,
                booking_id=booking.pk,
                **serializer.validated_data,
            )
        except DjangoValidationError as error:
            self.raise_service_error(error)

        result = BookingSerializer(
            booking,
            context=self.get_serializer_context(),
        )
        return Response(result.data)