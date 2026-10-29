from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
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
from loyalty.models import BonusTransaction, Membership, MembershipPlan
from notifications.models import Notification

from .events import BookingEventPublisher, BookingObserver
from .models import Booking, Payment
from .observers import BonusObserver, NotificationObserver
from .services import BookingConfirmationService, BookingService


class MembershipFailingObserver(BookingObserver):
    def update(self, event):
        raise RuntimeError("Тестова помилка після списання")


class MembershipConfirmationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="client")
        self.other_user = User.objects.create_user(username="other")

        center = SportsCenter.objects.create(
            name="Тестовий центр",
            address="Тестова адреса",
        )
        self.sport = SportType.objects.create(name="Йога")
        self.hall = Hall.objects.create(
            center=center,
            sport_type=self.sport,
            name="Зал йоги",
            capacity=10,
            hourly_price=Decimal("400.00"),
        )
        section = Section.objects.create(
            sport_type=self.sport,
            name="Йога для початківців",
            skill_level="beginner",
            age_category="adults",
        )
        trainer = Trainer.objects.create(
            full_name="Тестовий тренер",
            specialization="Йога",
        )

        now = timezone.now().replace(microsecond=0)
        self.starts_at = now + timedelta(days=10)

        session = TrainingSession.objects.create(
            section=section,
            hall=self.hall,
            trainer=trainer,
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(hours=1),
            capacity=10,
            price=Decimal("150.00"),
        )

        self.booking = BookingService.create_session_booking(
            user=self.user,
            session_id=session.pk,
        )

        self.plan = MembershipPlan.objects.create(
            name="Тестовий тариф",
            kind=MembershipPlan.Kind.MONTHLY,
            price=Decimal("1000.00"),
            validity_days=30,
            visit_limit=8,
            service_scope=MembershipPlan.ServiceScope.BOTH,
            sport_type=self.sport,
        )
        self.membership = Membership.objects.create(
            user=self.user,
            plan=self.plan,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=20),
            remaining_visits=8,
            status=Membership.Status.ACTIVE,
        )

    def confirm(self, booking=None, service=None):
        service = service or BookingConfirmationService()

        return service.confirm(
            (booking or self.booking).pk,
            settlement="membership",
            membership_id=self.membership.pk,
        )

    def assert_unchanged(self):
        self.membership.refresh_from_db()
        self.booking.refresh_from_db()

        self.assertEqual(self.booking.status, Booking.Status.PENDING)
        self.assertIsNone(self.booking.membership_id)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(BonusTransaction.objects.count(), 0)

    def test_session_consumes_one_use(self):
        result = self.confirm()
        self.membership.refresh_from_db()

        self.assertEqual(result.status, Booking.Status.CONFIRMED)
        self.assertEqual(result.membership_id, self.membership.pk)
        self.assertEqual(self.membership.remaining_visits, 7)
        self.assertEqual(result.payments.count(), 0)
        self.assertEqual(BonusTransaction.objects.count(), 0)
        self.assertEqual(
            Notification.objects.filter(
                booking=result,
                kind=Notification.Kind.BOOKING_CONFIRMED,
            ).count(),
            1,
        )

    def test_repeated_confirmation_does_not_consume_again(self):
        self.confirm()
        self.confirm()
        self.membership.refresh_from_db()

        self.assertEqual(self.membership.remaining_visits, 7)
        self.assertEqual(Notification.objects.count(), 1)

    def test_insufficient_uses_are_rejected(self):
        self.membership.remaining_visits = 0
        self.membership.save(update_fields=["remaining_visits"])

        with self.assertRaisesMessage(
            ValidationError,
            "недостатньо використань",
        ):
            self.confirm()

        self.assert_unchanged()
        self.assertEqual(self.membership.remaining_visits, 0)

    def test_another_users_membership_is_rejected(self):
        self.membership.user = self.other_user
        self.membership.save(update_fields=["user"])

        with self.assertRaisesMessage(
            ValidationError,
            "належить іншому користувачу",
        ):
            self.confirm()

        self.assert_unchanged()
        self.assertEqual(self.membership.remaining_visits, 8)

    def test_cancelled_membership_is_rejected(self):
        self.membership.status = Membership.Status.CANCELLED
        self.membership.save(update_fields=["status"])

        with self.assertRaisesMessage(
            ValidationError,
            "Абонемент скасовано",
        ):
            self.confirm()

        self.assert_unchanged()

    def test_membership_must_cover_entire_booking(self):
        self.membership.valid_until = (
            self.booking.ends_at - timedelta(minutes=1)
        )
        self.membership.save(update_fields=["valid_until"])

        with self.assertRaisesMessage(
            ValidationError,
            "не покриває весь період",
        ):
            self.confirm()

        self.assert_unchanged()

    def test_wrong_service_scope_is_rejected(self):
        self.plan.service_scope = MembershipPlan.ServiceScope.HALLS
        self.plan.save(update_fields=["service_scope"])

        with self.assertRaisesMessage(
            ValidationError,
            "не покриває цей вид послуги",
        ):
            self.confirm()

        self.assert_unchanged()

    def test_wrong_sport_is_rejected(self):
        self.plan.sport_type = SportType.objects.create(name="Футбол")
        self.plan.save(update_fields=["sport_type"])

        with self.assertRaisesMessage(
            ValidationError,
            "не поширюється на цей вид спорту",
        ):
            self.confirm()

        self.assert_unchanged()

    def test_unlimited_membership_keeps_empty_balance(self):
        self.plan.visit_limit = None
        self.plan.save(update_fields=["visit_limit"])
        self.membership.remaining_visits = None
        self.membership.save(update_fields=["remaining_visits"])

        result = self.confirm()
        self.membership.refresh_from_db()

        self.assertEqual(result.status, Booking.Status.CONFIRMED)
        self.assertIsNone(self.membership.remaining_visits)

    def test_ninety_minute_rental_consumes_two_uses(self):
        starts_at = self.starts_at + timedelta(days=1)

        rental = BookingService.create_hall_booking(
            user=self.user,
            hall_id=self.hall.pk,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=90),
        )

        result = self.confirm(booking=rental)
        self.membership.refresh_from_db()

        self.assertEqual(result.status, Booking.Status.CONFIRMED)
        self.assertEqual(self.membership.remaining_visits, 6)
        self.assertEqual(result.payments.count(), 0)

    def test_observer_failure_restores_membership_balance(self):
        publisher = BookingEventPublisher()
        publisher.subscribe(BonusObserver())
        publisher.subscribe(NotificationObserver())
        publisher.subscribe(MembershipFailingObserver())

        service = BookingConfirmationService(publisher=publisher)

        with self.assertRaisesMessage(
            RuntimeError,
            "Тестова помилка після списання",
        ):
            self.confirm(service=service)

        self.assert_unchanged()
        self.assertEqual(self.membership.remaining_visits, 8)

    def test_paid_booking_does_not_consume_membership(self):
        Payment.objects.create(
            booking=self.booking,
            amount=self.booking.total_price,
            status=Payment.Status.SUCCESS,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "вже має успішну оплату",
        ):
            self.confirm()

        self.assert_unchanged()
        self.assertEqual(self.membership.remaining_visits, 8)