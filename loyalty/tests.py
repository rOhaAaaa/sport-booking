from decimal import Decimal

from django.test import SimpleTestCase

from .strategies import (
    CorporateStrategy,
    PremiumStrategy,
    StandardStrategy,
)


class LoyaltyStrategyTests(SimpleTestCase):
    def test_prices(self):
        cases = [
            (StandardStrategy(), "Йога", "400.00"),
            (PremiumStrategy(), "Йога", "400.00"),
            (PremiumStrategy(), "Плавання", "0.00"),
            (PremiumStrategy(), " плавання ", "0.00"),
            (CorporateStrategy(), "Йога", "360.00"),
        ]

        for strategy, sport, expected in cases:
            with self.subTest(
                strategy=type(strategy).__name__,
                sport=sport,
            ):
                result = strategy.calculate_price(
                    Decimal("400.00"),
                    sport,
                )
                self.assertEqual(result, Decimal(expected))

    def test_bonuses(self):
        cases = [
            (StandardStrategy(), "400.00", 4),
            (PremiumStrategy(), "400.00", 20),
            (CorporateStrategy(), "360.00", 10),
            (PremiumStrategy(), "0.00", 0),
            (StandardStrategy(), "99.99", 0),
        ]

        for strategy, amount, expected in cases:
            with self.subTest(
                strategy=type(strategy).__name__,
                amount=amount,
            ):
                result = strategy.calculate_bonus(Decimal(amount))
                self.assertEqual(result, expected)

    def test_negative_amount_is_rejected(self):
        strategy = StandardStrategy()

        with self.assertRaises(ValueError):
            strategy.calculate_price(Decimal("-1.00"), "Йога")

        with self.assertRaises(ValueError):
            strategy.calculate_bonus(Decimal("-1.00"))