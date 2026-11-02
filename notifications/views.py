from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import (
    NotificationFilterSerializer,
    NotificationSerializer,
    OfferSerializer,
)
from .services import OfferService


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    filter_backends = []
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = (
            Notification.objects.filter(
                user=self.request.user,
            )
            .order_by("-created_at", "-pk")
        )

        if self.action == "list":
            filters = NotificationFilterSerializer(
                data=self.request.query_params,
                partial=True,
            )
            filters.is_valid(raise_exception=True)
            queryset = queryset.filter(
                **filters.validated_data,
            )

        return queryset

    @action(
        detail=True,
        methods=["post"],
        url_path="read",
        url_name="mark-read",
    )
    def mark_read(self, request, pk=None):
        notification = self.get_object()

        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])

        return Response(
            self.get_serializer(notification).data,
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="unread-count",
        url_name="unread-count",
    )
    def unread_count(self, request):
        count = self.get_queryset().filter(
            is_read=False,
        ).count()

        return Response({"unread_count": count})


class OfferViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = OfferSerializer
    filter_backends = []
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return OfferService.available_for_user(
            self.request.user,
        )