from rest_framework.routers import DefaultRouter

from .views import (
    HallViewSet,
    SectionViewSet,
    SportsCenterViewSet,
    SportTypeViewSet,
    TrainerViewSet,
    TrainingSessionViewSet,
)


router = DefaultRouter()
router.register(
    "centers",
    SportsCenterViewSet,
    basename="center",
)
router.register(
    "sport-types",
    SportTypeViewSet,
    basename="sport-type",
)
router.register(
    "halls",
    HallViewSet,
    basename="hall",
)
router.register(
    "sections",
    SectionViewSet,
    basename="section",
)
router.register(
    "trainers",
    TrainerViewSet,
    basename="trainer",
)
router.register(
    "sessions",
    TrainingSessionViewSet,
    basename="session",
)

urlpatterns = router.urls