from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


def _money(value):
    if not isinstance(value, Decimal):
        raise TypeError("Грошова сума має бути об’єктом Decimal.")

    if not value.is_finite() or value < 0:
        raise ValueError("Грошова сума має бути невід’ємним числом.")

    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _bonus(amount, rate):
    result = _money(amount) * rate
    return int(result.to_integral_value(rounding=ROUND_DOWN))


class LoyaltyStrategy(ABC):
    @abstractmethod
    def calculate_price(self, base_price, sport_type):
        pass

    @abstractmethod
    def calculate_bonus(self, amount):
        pass


class StandardStrategy(LoyaltyStrategy):
    def calculate_price(self, base_price, sport_type):
        return _money(base_price)

    def calculate_bonus(self, amount):
        return _bonus(amount, Decimal("0.01"))


class PremiumStrategy(LoyaltyStrategy):
    def calculate_price(self, base_price, sport_type):
        price = _money(base_price)

        if sport_type.strip().casefold() == "плавання":
            return Decimal("0.00")

        return price

    def calculate_bonus(self, amount):
        return _bonus(amount, Decimal("0.05"))


class CorporateStrategy(LoyaltyStrategy):
    def calculate_price(self, base_price, sport_type):
        price = _money(base_price)
        return _money(price * Decimal("0.90"))

    def calculate_bonus(self, amount):
        return _bonus(amount, Decimal("0.03"))