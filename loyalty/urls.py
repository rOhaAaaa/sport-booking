from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BonusTransactionViewSet,
    MembershipPlanViewSet,
    MembershipViewSet,
    OwnLoyaltyCardView,
)


app_name = "loyalty"

router = DefaultRouter()
router.register(
    "plans",
    MembershipPlanViewSet,
    basename="plan",
)
router.register(
    "memberships",
    MembershipViewSet,
    basename="membership",
)
router.register(
    "bonuses",
    BonusTransactionViewSet,
    basename="bonus",
)

urlpatterns = [
    path(
        "card/",
        OwnLoyaltyCardView.as_view(),
        name="card",
    ),
    path("", include(router.urls)),
]