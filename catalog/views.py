from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ReadOnlyModelViewSet
from .filters import HallFilter, SectionFilter, TrainingSessionFilter

from .models import (
    Hall,
    Section,
    SportsCenter,
    SportType,
    Trainer,
    TrainingSession,
)
from .serializers import (
    HallSerializer,
    SectionSerializer,
    SportsCenterSerializer,
    SportTypeSerializer,
    TrainerSerializer,
    TrainingSessionSerializer,
)


class PublicCatalogViewSet(ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]


class SportsCenterViewSet(PublicCatalogViewSet):
    queryset = SportsCenter.objects.all().order_by("name", "pk")
    serializer_class = SportsCenterSerializer


class SportTypeViewSet(PublicCatalogViewSet):
    queryset = SportType.objects.all().order_by("name", "pk")
    serializer_class = SportTypeSerializer


class HallViewSet(PublicCatalogViewSet):
    queryset = (
        Hall.objects.select_related("center", "sport_type")
        .order_by("name", "pk")
    )
    serializer_class = HallSerializer
    filterset_class = HallFilter


class SectionViewSet(PublicCatalogViewSet):
    queryset = (
        Section.objects.select_related("sport_type")
        .order_by("name", "pk")
    )
    serializer_class = SectionSerializer
    filterset_class = SectionFilter


class TrainerViewSet(PublicCatalogViewSet):
    queryset = Trainer.objects.all().order_by("full_name", "pk")
    serializer_class = TrainerSerializer


class TrainingSessionViewSet(PublicCatalogViewSet):
    queryset = (
        TrainingSession.objects.select_related(
            "section__sport_type",
            "hall",
            "trainer",
        )
        .order_by("starts_at", "pk")
    )
    serializer_class = TrainingSessionSerializer
    filterset_class = TrainingSessionFilter