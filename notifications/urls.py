from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet, OfferViewSet


app_name = "notifications"

router = DefaultRouter()
router.register(
    "messages",
    NotificationViewSet,
    basename="notification",
)
router.register(
    "offers",
    OfferViewSet,
    basename="offer",
)

urlpatterns = router.urls