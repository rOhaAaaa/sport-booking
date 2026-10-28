from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from catalog.models import Hall, TrainingSession
from loyalty.services import LoyaltyService

from .models import Booking


ACTIVE_STATUSES = (
    Booking.Status.PENDING,
    Booking.Status.CONFIRMED,
)


def validate_period(starts_at, ends_at):
    if not isinstance(starts_at, datetime):
        raise ValidationError("Потрібно вказати дату й час початку.")

    if not isinstance(ends_at, datetime):
        raise ValidationError("Потрібно вказати дату й час завершення.")

    if timezone.is_naive(starts_at) or timezone.is_naive(ends_at):
        raise ValidationError(
            "Дата й час мають містити інформацію про часовий пояс."
        )

    if ends_at <= starts_at:
        raise ValidationError(
            "Завершення має бути пізніше за початок."
        )

    if starts_at <= timezone.now():
        raise ValidationError(
            "Бронювання потрібно створювати на майбутній час."
        )


class BookingProcessor(ABC):
    def create_booking(self, user, data):
        if not isinstance(data, dict):
            raise ValidationError("Дані бронювання мають бути словником.")

        data = data.copy()

        with transaction.atomic():
            self.validate_input(user, data)
            self.check_availability(user, data)
            price = self.calculate_price(user, data)
            return self.save_booking(user, data, price)

    def validate_input(self, user, data):
        if (
            not user.is_authenticated
            or not user.is_active
            or user.pk is None
        ):
            raise ValidationError(
                "Бронювання доступне лише активному "
                "авторизованому користувачу."
            )

    @abstractmethod
    def check_availability(self, user, data):
        pass

    @abstractmethod
    def calculate_price(self, user, data):
        pass

    def save_booking(self, user, data, price):
        booking = Booking(
            user=user,
            hall=data["hall"],
            session=data["session"],
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
            total_price=price,
            status=Booking.Status.PENDING,
        )
        booking.full_clean()
        booking.save()
        return booking


class HallBookingProcessor(BookingProcessor):
    def validate_input(self, user, data):
        super().validate_input(user, data)

        try:
            hall = Hall.objects.select_related("sport_type").get(
                pk=data.get("hall_id"),
            )
        except (Hall.DoesNotExist, ValueError, TypeError):
            raise ValidationError("Вибраний зал не знайдено.")

        validate_period(
            data.get("starts_at"),
            data.get("ends_at"),
        )

        data["hall"] = hall
        data["session"] = None

    def check_availability(self, user, data):
        hall = data["hall"]
        starts_at = data["starts_at"]
        ends_at = data["ends_at"]

        overlapping_bookings = Booking.objects.filter(
            hall=hall,
            status__in=ACTIVE_STATUSES,
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )

        if overlapping_bookings.exists():
            raise ValidationError(
                "Зал уже заброньовано на вибраний час."
            )

        overlapping_sessions = TrainingSession.objects.filter(
            hall=hall,
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )

        if overlapping_sessions.exists():
            raise ValidationError(
                "На вибраний час у залі заплановано заняття."
            )

    def calculate_price(self, user, data):
        duration = data["ends_at"] - data["starts_at"]
        microseconds = duration // timedelta(microseconds=1)
        hours = Decimal(microseconds) / Decimal("3600000000")
        base_price = data["hall"].hourly_price * hours

        service = LoyaltyService.for_user(user)
        return service.calculate_price(
            base_price,
            data["hall"].sport_type.name,
        )


class SessionBookingProcessor(BookingProcessor):
    def validate_input(self, user, data):
        super().validate_input(user, data)

        try:
            session = TrainingSession.objects.select_related(
                "hall",
                "section__sport_type",
            ).get(pk=data.get("session_id"))
        except (TrainingSession.DoesNotExist, ValueError, TypeError):
            raise ValidationError("Вибране заняття не знайдено.")

        validate_period(session.starts_at, session.ends_at)

        data["hall"] = None
        data["session"] = session
        data["starts_at"] = session.starts_at
        data["ends_at"] = session.ends_at

    def check_availability(self, user, data):
        session = data["session"]

        active_bookings = Booking.objects.filter(
            session=session,
            status__in=ACTIVE_STATUSES,
        )

        if active_bookings.filter(user=user).exists():
            raise ValidationError(
                "Користувач уже має активне бронювання "
                "на це заняття."
            )

        if active_bookings.count() >= session.capacity:
            raise ValidationError(
                "На занятті немає вільних місць."
            )

        overlapping_rentals = Booking.objects.filter(
            hall=session.hall,
            status__in=ACTIVE_STATUSES,
            starts_at__lt=session.ends_at,
            ends_at__gt=session.starts_at,
        )

        if overlapping_rentals.exists():
            raise ValidationError(
                "Зал зайнятий орендою на час заняття."
            )

    def calculate_price(self, user, data):
        session = data["session"]
        service = LoyaltyService.for_user(user)

        return service.calculate_price(
            session.price,
            session.section.sport_type.name,
        )