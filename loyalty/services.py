from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import LoyaltyCard, Membership, MembershipPlan
from .strategies import (
    CorporateStrategy,
    PremiumStrategy,
    StandardStrategy,
)


class LoyaltyService:
    def __init__(self, strategy):
        self.strategy = strategy

    @classmethod
    def for_user(cls, user):
        try:
            category = user.loyalty_card.category
        except LoyaltyCard.DoesNotExist:
            category = LoyaltyCard.Category.STANDARD

        strategies = {
            LoyaltyCard.Category.STANDARD: StandardStrategy,
            LoyaltyCard.Category.PREMIUM: PremiumStrategy,
            LoyaltyCard.Category.CORPORATE: CorporateStrategy,
        }

        strategy_class = strategies.get(category)

        if strategy_class is None:
            raise ValueError("Невідома категорія картки лояльності.")

        return cls(strategy_class())

    def calculate_price(self, base_price, sport_type):
        return self.strategy.calculate_price(
            base_price,
            sport_type,
        )

    def calculate_bonus(self, amount):
        return self.strategy.calculate_bonus(amount)

class MembershipService:
    @staticmethod
    def purchase(user, plan_id, payment_successful=False):
        if (
            not user.is_authenticated
            or not user.is_active
            or user.pk is None
        ):
            raise ValidationError(
                "Придбання абонемента доступне лише "
                "активному авторизованому користувачу."
            )

        if payment_successful is not True:
            raise ValidationError(
                "Імітована оплата неуспішна. "
                "Абонемент не створено."
            )

        with transaction.atomic():
            try:
                plan = MembershipPlan.objects.get(pk=plan_id)
            except (MembershipPlan.DoesNotExist, ValueError, TypeError):
                raise ValidationError("Тариф абонемента не знайдено.")

            plan.full_clean()
            starts_at = timezone.now()

            membership = Membership(
                user=user,
                plan=plan,
                valid_from=starts_at,
                valid_until=starts_at + timedelta(
                    days=plan.validity_days,
                ),
                remaining_visits=plan.visit_limit,
                status=Membership.Status.ACTIVE,
            )
            membership.full_clean()
            membership.save()

            return membership