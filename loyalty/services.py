from .models import LoyaltyCard
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