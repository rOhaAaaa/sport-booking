from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from rest_framework import (
    generics,
    mixins,
    serializers,
    status,
    viewsets,
)
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import (
    BonusTransaction,
    LoyaltyCard,
    Membership,
    MembershipPlan,
)
from .serializers import (
    BonusTransactionSerializer,
    LoyaltyCardSerializer,
    MembershipPlanSerializer,
    MembershipPurchaseSerializer,
    MembershipSerializer,
)
from .services import MembershipService


class MembershipPlanViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]
    serializer_class = MembershipPlanSerializer
    filter_backends = []
    queryset = (
        MembershipPlan.objects.select_related("sport_type")
        .order_by("name", "pk")
    )


class MembershipViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = MembershipSerializer
    filter_backends = []
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            Membership.objects.filter(user=self.request.user)
            .select_related("plan__sport_type")
            .order_by("-valid_from", "-pk")
        )

    def get_serializer_class(self):
        if self.action == "purchase":
            return MembershipPurchaseSerializer
        return MembershipSerializer

    @action(
        detail=False,
        methods=["post"],
        url_path="purchase",
        url_name="purchase",
    )
    def purchase(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            membership = MembershipService.purchase(
                user=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as error:
            if hasattr(error, "message_dict"):
                detail = error.message_dict
            else:
                detail = {
                    "non_field_errors": error.messages,
                }
            raise serializers.ValidationError(detail) from error

        result = MembershipSerializer(
            membership,
            context=self.get_serializer_context(),
        )
        return Response(
            result.data,
            status=status.HTTP_201_CREATED,
        )


class OwnLoyaltyCardView(generics.RetrieveAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = LoyaltyCardSerializer

    def get_object(self):
        card, _ = LoyaltyCard.objects.get_or_create(
            user=self.request.user,
            defaults={
                "category": LoyaltyCard.Category.STANDARD,
            },
        )
        self.check_object_permissions(self.request, card)
        return card


class BonusTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = BonusTransactionSerializer
    filter_backends = []

    def get_queryset(self):
        return (
            BonusTransaction.objects.filter(
                card__user=self.request.user,
            )
            .select_related("booking")
            .order_by("-created_at", "-pk")
        )