from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from catalog.models import Hall, SportsCenter, SportType
from loyalty.models import BonusTransaction, LoyaltyCard
from notifications.models import Notification

from .events import BookingEventPublisher, BookingObserver
from .models import Booking, Payment
from .observers import BonusObserver, NotificationObserver
from .services import BookingConfirmationService, BookingService


class FailingObserver(BookingObserver):
    def update(self, event):
        raise RuntimeError("Тестова помилка спостерігача")


class BookingConfirmationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="premium_client",
        )
        self.card = LoyaltyCard.objects.create(
            user=self.user,
            category=LoyaltyCard.Category.PREMIUM,
        )
        self.center = SportsCenter.objects.create(
            name="Тестовий центр",
            address="Тестова адреса",
        )
        self.sport = SportType.objects.create(name="Йога")
        self.hall = Hall.objects.create(
            center=self.center,
            sport_type=self.sport,
            name="Зал йоги",
            capacity=10,
            hourly_price=Decimal("400.00"),
        )

        self.starts_at = (
            timezone.now() + timedelta(days=10)
        ).replace(microsecond=0)

        self.booking = BookingService.create_hall_booking(
            user=self.user,
            hall_id=self.hall.pk,
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(hours=1),
        )

    def create_successful_payment(self):
        payment = Payment(
            booking=self.booking,
            amount=self.booking.total_price,
            status=Payment.Status.SUCCESS,
        )
        payment.full_clean()
        payment.save()
        return payment

    def test_paid_booking_creates_bonus_and_notifications(self):
        self.create_successful_payment()

        result = BookingConfirmationService().confirm(
            self.booking.pk,
        )

        self.booking.refresh_from_db()
        bonus = BonusTransaction.objects.get(
            booking=self.booking,
        )

        self.assertEqual(result.pk, self.booking.pk)
        self.assertEqual(
            self.booking.status,
            Booking.Status.CONFIRMED,
        )
        self.assertEqual(bonus.card_id, self.card.pk)
        self.assertEqual(bonus.points, 20)
        self.assertEqual(
            Notification.objects.filter(
                booking=self.booking,
                kind=Notification.Kind.BONUS,
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                booking=self.booking,
                kind=Notification.Kind.BOOKING_CONFIRMED,
            ).count(),
            1,
        )

    def test_repeated_confirmation_does_not_create_duplicates(self):
        self.create_successful_payment()
        service = BookingConfirmationService()

        service.confirm(self.booking.pk)
        service.confirm(self.booking.pk)

        self.assertEqual(
            BonusTransaction.objects.filter(
                booking=self.booking,
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                booking=self.booking,
            ).count(),
            2,
        )

    def test_unpaid_booking_is_not_confirmed(self):
        with self.assertRaisesMessage(
            ValidationError,
            "потрібна успішна оплата",
        ):
            BookingConfirmationService().confirm(self.booking.pk)

        self.booking.refresh_from_db()
        self.assertEqual(
            self.booking.status,
            Booking.Status.PENDING,
        )
        self.assertEqual(BonusTransaction.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_cancelled_booking_is_not_confirmed(self):
        self.create_successful_payment()
        self.booking.status = Booking.Status.CANCELLED
        self.booking.save(update_fields=["status"])

        with self.assertRaisesMessage(
            ValidationError,
            "Скасоване бронювання",
        ):
            BookingConfirmationService().confirm(self.booking.pk)

        self.assertEqual(BonusTransaction.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_incorrect_payment_amount_is_rejected(self):
        payment = self.create_successful_payment()

        Payment.objects.filter(pk=payment.pk).update(
            amount=Decimal("300.00"),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Сума успішної оплати не відповідає",
        ):
            BookingConfirmationService().confirm(self.booking.pk)

        self.booking.refresh_from_db()
        self.assertEqual(
            self.booking.status,
            Booking.Status.PENDING,
        )
        self.assertEqual(BonusTransaction.objects.count(), 0)

    def test_observer_failure_rolls_back_all_effects(self):
        self.create_successful_payment()

        publisher = BookingEventPublisher()
        publisher.subscribe(BonusObserver())
        publisher.subscribe(NotificationObserver())
        publisher.subscribe(FailingObserver())

        service = BookingConfirmationService(
            publisher=publisher,
        )

        with self.assertRaisesMessage(
            RuntimeError,
            "Тестова помилка спостерігача",
        ):
            service.confirm(self.booking.pk)

        self.booking.refresh_from_db()
        self.assertEqual(
            self.booking.status,
            Booking.Status.PENDING,
        )
        self.assertEqual(BonusTransaction.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(
            Payment.objects.filter(
                booking=self.booking,
                status=Payment.Status.SUCCESS,
            ).count(),
            1,
        )

    def test_premium_swimming_is_confirmed_without_payment(self):
        swimming = SportType.objects.create(name="Плавання")
        pool = Hall.objects.create(
            center=self.center,
            sport_type=swimming,
            name="Басейн",
            capacity=10,
            hourly_price=Decimal("800.00"),
        )

        booking = BookingService.create_hall_booking(
            user=self.user,
            hall_id=pool.pk,
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(hours=1),
        )

        result = BookingConfirmationService().confirm(
            booking.pk,
            settlement="free",
        )

        self.assertEqual(result.total_price, Decimal("0.00"))
        self.assertEqual(result.status, Booking.Status.CONFIRMED)
        self.assertEqual(result.payments.count(), 0)
        self.assertEqual(BonusTransaction.objects.count(), 0)
        self.assertEqual(
            Notification.objects.filter(
                booking=booking,
                kind=Notification.Kind.BOOKING_CONFIRMED,
            ).count(),
            1,
        )

    def test_zero_price_alone_does_not_grant_free_service(self):
        Booking.objects.filter(pk=self.booking.pk).update(
            total_price=Decimal("0.00"),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "не має права",
        ):
            BookingConfirmationService().confirm(
                self.booking.pk,
                settlement="free",
            )

        self.booking.refresh_from_db()
        self.assertEqual(
            self.booking.status,
            Booking.Status.PENDING,
        )
        self.assertEqual(Notification.objects.count(), 0)