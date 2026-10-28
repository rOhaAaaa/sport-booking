from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from catalog.models import (
    Hall,
    Section,
    SportsCenter,
    SportType,
    Trainer,
    TrainingSession,
)
from loyalty.models import LoyaltyCard

from .models import Booking
from .services import BookingService


class BookingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="client")
        cls.other_user = User.objects.create_user(username="other")

        cls.center = SportsCenter.objects.create(
            name="Тестовий центр",
            address="Тестова адреса",
        )
        cls.sport = SportType.objects.create(name="Йога")

        cls.hall = Hall.objects.create(
            center=cls.center,
            sport_type=cls.sport,
            name="Тестовий зал",
            capacity=10,
            hourly_price=Decimal("400.00"),
        )
        cls.section = Section.objects.create(
            sport_type=cls.sport,
            name="Тестова секція",
            skill_level="beginner",
            age_category="adults",
        )
        cls.trainer = Trainer.objects.create(
            full_name="Тестовий тренер",
            specialization="Йога",
        )

        cls.starts_at = (
            timezone.now() + timedelta(days=10)
        ).replace(microsecond=0)

        cls.session = TrainingSession.objects.create(
            section=cls.section,
            hall=cls.hall,
            trainer=cls.trainer,
            starts_at=cls.starts_at + timedelta(days=1),
            ends_at=cls.starts_at + timedelta(days=1, hours=1),
            capacity=1,
            price=Decimal("150.00"),
        )

    def create_rental(self, user=None, starts_at=None, ends_at=None):
        return BookingService.create_hall_booking(
            user=user or self.user,
            hall_id=self.hall.pk,
            starts_at=starts_at or self.starts_at,
            ends_at=ends_at or self.starts_at + timedelta(hours=1),
        )

    def test_hall_price_depends_on_duration(self):
        booking = self.create_rental(
            ends_at=self.starts_at + timedelta(minutes=90),
        )

        self.assertEqual(booking.total_price, Decimal("600.00"))
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.hall_id, self.hall.pk)
        self.assertIsNone(booking.session_id)
        self.assertEqual(Booking.objects.count(), 1)

    def test_corporate_discount_is_applied(self):
        LoyaltyCard.objects.create(
            user=self.user,
            category=LoyaltyCard.Category.CORPORATE,
        )

        booking = self.create_rental()

        self.assertEqual(booking.total_price, Decimal("360.00"))

    def test_overlapping_rental_is_rejected(self):
        self.create_rental()

        with self.assertRaisesMessage(
            ValidationError,
            "Зал уже заброньовано",
        ):
            self.create_rental(
                user=self.other_user,
                starts_at=self.starts_at + timedelta(minutes=30),
                ends_at=self.starts_at + timedelta(minutes=90),
            )

        self.assertEqual(Booking.objects.count(), 1)

    def test_adjacent_rental_is_allowed(self):
        self.create_rental()

        booking = self.create_rental(
            user=self.other_user,
            starts_at=self.starts_at + timedelta(hours=1),
            ends_at=self.starts_at + timedelta(hours=2),
        )

        self.assertIsNotNone(booking.pk)
        self.assertEqual(Booking.objects.count(), 2)

    def test_scheduled_session_blocks_hall_rental(self):
        with self.assertRaisesMessage(
            ValidationError,
            "заплановано заняття",
        ):
            self.create_rental(
                starts_at=self.session.starts_at,
                ends_at=self.session.ends_at,
            )

        self.assertEqual(Booking.objects.count(), 0)

    def test_session_uses_its_price_and_dates(self):
        booking = BookingService.create_session_booking(
            user=self.user,
            session_id=self.session.pk,
        )

        self.assertEqual(booking.total_price, Decimal("150.00"))
        self.assertEqual(booking.starts_at, self.session.starts_at)
        self.assertEqual(booking.ends_at, self.session.ends_at)
        self.assertEqual(booking.session_id, self.session.pk)
        self.assertIsNone(booking.hall_id)

    def test_duplicate_session_booking_is_rejected(self):
        BookingService.create_session_booking(
            user=self.user,
            session_id=self.session.pk,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "уже має активне бронювання",
        ):
            BookingService.create_session_booking(
                user=self.user,
                session_id=self.session.pk,
            )

        self.assertEqual(Booking.objects.count(), 1)

    def test_full_session_is_rejected(self):
        BookingService.create_session_booking(
            user=self.user,
            session_id=self.session.pk,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "немає вільних місць",
        ):
            BookingService.create_session_booking(
                user=self.other_user,
                session_id=self.session.pk,
            )

        self.assertEqual(Booking.objects.count(), 1)

    def test_cancelled_rental_does_not_block_hall(self):
        booking = self.create_rental()
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status"])

        replacement = self.create_rental(user=self.other_user)

        self.assertIsNotNone(replacement.pk)

    def test_anonymous_user_is_rejected(self):
        with self.assertRaisesMessage(
            ValidationError,
            "авторизованому користувачу",
        ):
            self.create_rental(user=AnonymousUser())

        self.assertEqual(Booking.objects.count(), 0)

    def test_past_start_is_rejected(self):
        with self.assertRaisesMessage(
            ValidationError,
            "на майбутній час",
        ):
            self.create_rental(
                starts_at=timezone.now() - timedelta(hours=2),
                ends_at=timezone.now() - timedelta(hours=1),
            )

        self.assertEqual(Booking.objects.count(), 0)