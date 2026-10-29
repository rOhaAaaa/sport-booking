from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .events import BookingConfirmedEvent, BookingEventPublisher
from .models import Booking, Payment
from .observers import BonusObserver, NotificationObserver
from .processors import (
    HallBookingProcessor,
    SessionBookingProcessor,
)


class BookingService:
    @staticmethod
    def create_hall_booking(user, hall_id, starts_at, ends_at):
        processor = HallBookingProcessor()

        return processor.create_booking(
            user,
            {
                "hall_id": hall_id,
                "starts_at": starts_at,
                "ends_at": ends_at,
            },
        )

    @staticmethod
    def create_session_booking(user, session_id):
        processor = SessionBookingProcessor()

        return processor.create_booking(
            user,
            {"session_id": session_id},
        )

class BookingConfirmationService:
    def __init__(self, publisher=None):
        if publisher is None:
            publisher = BookingEventPublisher()
            publisher.subscribe(BonusObserver())
            publisher.subscribe(NotificationObserver())

        self.publisher = publisher

    def confirm(self, booking_id, settlement="payment"):
        if settlement not in {"payment", "free"}:
            raise ValidationError(
                "Непідтримуваний спосіб підтвердження."
            )

        with transaction.atomic():
            try:
                booking = Booking.objects.select_related(
                    "user",
                    "hall__sport_type",
                    "session__section__sport_type",
                ).get(pk=booking_id)
            except (Booking.DoesNotExist, ValueError, TypeError):
                raise ValidationError("Бронювання не знайдено.")

            if booking.status == Booking.Status.CONFIRMED:
                return booking

            if booking.status == Booking.Status.CANCELLED:
                raise ValidationError(
                    "Скасоване бронювання не можна підтвердити."
                )

            if booking.starts_at <= timezone.now():
                raise ValidationError(
                    "Не можна підтвердити бронювання, "
                    "час початку якого вже настав."
                )

            if booking.membership_id is not None:
                raise ValidationError(
                    "Для цього бронювання потрібно застосувати "
                    "окремий сценарій використання абонемента."
                )

            booking.full_clean()

            if settlement == "payment":
                self._validate_payment(booking)
            else:
                self._validate_free_service(booking)

            booking.status = Booking.Status.CONFIRMED
            booking.save(update_fields=["status"])

            event = BookingConfirmedEvent(
                booking_id=booking.pk,
            )
            self.publisher.notify(event)

            return booking

    def _validate_payment(self, booking):
        payment = booking.payments.filter(
            status=Payment.Status.SUCCESS,
        ).first()

        if payment is None:
            raise ValidationError(
                "Для підтвердження потрібна успішна оплата."
            )

        if booking.total_price <= 0:
            raise ValidationError(
                "Безкоштовна послуга підтверджується "
                "без створення оплати."
            )

        if payment.amount != booking.total_price:
            raise ValidationError(
                "Сума успішної оплати не відповідає "
                "вартості бронювання."
            )

    def _validate_free_service(self, booking):
        if booking.total_price != Decimal("0.00"):
            raise ValidationError(
                "Вартість безкоштовної послуги "
                "має дорівнювати нулю."
            )

        if booking.payments.filter(
            status=Payment.Status.SUCCESS,
        ).exists():
            raise ValidationError(
                "Бронювання вже має успішну оплату."
            )

        if booking.hall_id is not None:
            processor = HallBookingProcessor()
            data = {
                "hall": booking.hall,
                "starts_at": booking.starts_at,
                "ends_at": booking.ends_at,
            }
        else:
            processor = SessionBookingProcessor()
            data = {"session": booking.session}

        current_price = processor.calculate_price(
            booking.user,
            data,
        )

        if current_price != Decimal("0.00"):
            raise ValidationError(
                "Користувач не має права отримати "
                "цю послугу безкоштовно."
            )