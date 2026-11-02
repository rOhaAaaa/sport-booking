from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from bookings.models import Booking
from loyalty.models import LoyaltyCard

from .models import Notification, Offer



class ReminderService:
    @staticmethod
    def create_upcoming_reminders(hours=24):
        if type(hours) is not int or not 1 <= hours <= 720:
            raise ValueError(
                "Період нагадувань має бути цілим числом "
                "від 1 до 720 годин."
            )

        now = timezone.now()
        deadline = now + timedelta(hours=hours)
        created_count = 0

        with transaction.atomic():
            bookings = (
                Booking.objects.filter(
                    status=Booking.Status.CONFIRMED,
                    session__isnull=False,
                    user__is_active=True,
                    starts_at__gt=now,
                    starts_at__lte=deadline,
                )
                .select_related(
                    "user",
                    "session__section",
                    "session__hall",
                )
                .order_by("starts_at", "pk")
            )

            for booking in bookings:
                starts_at = timezone.localtime(
                    booking.starts_at
                ).strftime("%d.%m.%Y о %H:%M")

                _, created = Notification.objects.get_or_create(
                    booking=booking,
                    kind=Notification.Kind.REMINDER,
                    defaults={
                        "user": booking.user,
                        "message": (
                            f'Нагадуємо про заняття '
                            f'«{booking.session.section.name}» '
                            f'{starts_at}. '
                            f'Зал: {booking.session.hall.name}. '
                            f'Бронювання №{booking.pk}.'
                        ),
                    },
                )

                created_count += int(created)

        return created_count

class OfferService:
    @staticmethod
    def available_for_user(user):
        if (
            not user.is_authenticated
            or not user.is_active
            or user.pk is None
        ):
            return Offer.objects.none()

        category = (
            LoyaltyCard.objects.filter(user=user)
            .values_list("category", flat=True)
            .first()
        )

        if category is None:
            category = LoyaltyCard.Category.STANDARD

        now = timezone.now()

        return (
            Offer.objects.filter(
                starts_at__lte=now,
                ends_at__gt=now,
                target_card_category__in=(
                    Offer.TargetCategory.ALL,
                    category,
                ),
            )
            .order_by("-starts_at", "-pk")
        )