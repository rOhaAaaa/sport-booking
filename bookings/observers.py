from decimal import Decimal

from django.core.exceptions import ValidationError

from loyalty.models import BonusTransaction, LoyaltyCard
from loyalty.services import LoyaltyService
from notifications.models import Notification

from .events import BookingObserver
from .models import Booking, Payment


def get_confirmed_booking(booking_id):
    booking = Booking.objects.select_related("user").get(
        pk=booking_id,
    )

    if booking.status != Booking.Status.CONFIRMED:
        raise ValidationError(
            "Подію можна обробляти лише "
            "для підтвердженого бронювання."
        )

    return booking


class BonusObserver(BookingObserver):
    def update(self, event):
        booking = get_confirmed_booking(event.booking_id)

        payment = booking.payments.filter(
            status=Payment.Status.SUCCESS,
        ).first()

        paid_amount = (
            payment.amount
            if payment is not None
            else Decimal("0.00")
        )

        service = LoyaltyService.for_user(booking.user)
        points = service.calculate_bonus(paid_amount)

        if points <= 0:
            return

        card, _ = LoyaltyCard.objects.get_or_create(
            user=booking.user,
            defaults={
                "category": LoyaltyCard.Category.STANDARD,
            },
        )

        bonus, created = BonusTransaction.objects.get_or_create(
            booking=booking,
            defaults={
                "card": card,
                "points": points,
            },
        )

        if created:
            Notification.objects.get_or_create(
                user=booking.user,
                kind=Notification.Kind.BONUS,
                booking=booking,
                defaults={
                    "message": (
                        f"За бронювання №{booking.pk} "
                        f"нараховано {bonus.points} бонусних балів."
                    ),
                },
            )


class NotificationObserver(BookingObserver):
    def update(self, event):
        booking = get_confirmed_booking(event.booking_id)

        Notification.objects.get_or_create(
            user=booking.user,
            kind=Notification.Kind.BOOKING_CONFIRMED,
            booking=booking,
            defaults={
                "message": (
                    f"Ваше бронювання №{booking.pk} підтверджено."
                ),
            },
        )