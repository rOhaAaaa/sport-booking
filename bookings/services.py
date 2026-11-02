from decimal import Decimal
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.db.models import F

from .events import BookingConfirmedEvent, BookingEventPublisher
from .models import Booking, Payment
from .observers import BonusObserver, NotificationObserver
from loyalty.models import Membership, MembershipPlan
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

    def confirm(
        self,
        booking_id,
        settlement="payment",
        membership_id=None,
    ):
        if settlement not in {"payment", "free", "membership"}:
            raise ValidationError(
                "Непідтримуваний спосіб підтвердження."
            )

        if settlement == "membership" and membership_id is None:
            raise ValidationError("Потрібно вибрати абонемент.")

        if settlement != "membership" and membership_id is not None:
            raise ValidationError(
                "Абонемент передається лише для способу "
                "підтвердження membership."
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

            if (
                booking.membership_id is not None
                and settlement != "membership"
            ):
                raise ValidationError(
                    "Для бронювання з абонементом оберіть "
                    "відповідний спосіб підтвердження."
                )

            booking.full_clean()

            if settlement == "payment":
                self._validate_payment(booking)
            elif settlement == "free":
                self._validate_free_service(booking)
            else:
                self._apply_membership(booking, membership_id)

            booking.status = Booking.Status.CONFIRMED
            booking.full_clean()
            booking.save(update_fields=["status", "membership"])

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

    def _apply_membership(self, booking, membership_id):
        if booking.payments.filter(
            status=Payment.Status.SUCCESS,
        ).exists():
            raise ValidationError(
                "Бронювання вже має успішну оплату. "
                "Додаткове списання абонемента не потрібне."
            )

        if booking.total_price <= 0:
            raise ValidationError(
                "Безкоштовну послугу потрібно підтвердити "
                "без списання абонемента."
            )

        try:
            membership = Membership.objects.select_related(
                "plan",
            ).get(pk=membership_id)
        except (Membership.DoesNotExist, ValueError, TypeError):
            raise ValidationError("Абонемент не знайдено.")

        if (
            booking.membership_id is not None
            and booking.membership_id != membership.pk
        ):
            raise ValidationError(
                "У бронюванні вже зазначено інший абонемент."
            )

        if membership.user_id != booking.user_id:
            raise ValidationError(
                "Абонемент належить іншому користувачу."
            )

        if membership.status != Membership.Status.ACTIVE:
            raise ValidationError("Абонемент скасовано.")

        if (
            booking.starts_at < membership.valid_from
            or booking.ends_at > membership.valid_until
        ):
            raise ValidationError(
                "Строк дії абонемента не покриває "
                "весь період бронювання."
            )

        membership.full_clean()
        plan = membership.plan

        if booking.session_id is not None:
            required_scope = MembershipPlan.ServiceScope.SESSIONS
            sport_type_id = booking.session.section.sport_type_id
            required_uses = 1
        else:
            required_scope = MembershipPlan.ServiceScope.HALLS
            sport_type_id = booking.hall.sport_type_id

            duration = booking.ends_at - booking.starts_at
            whole_hours, remainder = divmod(
                duration,
                timedelta(hours=1),
            )
            required_uses = whole_hours + (1 if remainder else 0)

        if plan.service_scope not in {
            required_scope,
            MembershipPlan.ServiceScope.BOTH,
        }:
            raise ValidationError(
                "Тариф абонемента не покриває цей вид послуги."
            )

        if (
            plan.sport_type_id is not None
            and plan.sport_type_id != sport_type_id
        ):
            raise ValidationError(
                "Абонемент не поширюється на цей вид спорту."
            )

        if membership.remaining_visits is not None:
            updated = Membership.objects.filter(
                pk=membership.pk,
                remaining_visits__gte=required_uses,
            ).update(
                remaining_visits=F("remaining_visits") - required_uses,
            )

            if updated != 1:
                raise ValidationError(
                    "В абонементі недостатньо використань."
                )

        booking.membership = membership

class BookingCheckoutService:
    @staticmethod
    def confirm(
        user,
        booking_id,
        settlement,
        membership_id=None,
        payment_successful=None,
    ):
        if (
            not user.is_authenticated
            or not user.is_active
            or user.pk is None
        ):
            raise ValidationError(
                "Потрібно увійти в активний обліковий запис."
            )

        if settlement not in {"payment", "membership", "free"}:
            raise ValidationError(
                "Непідтримуваний спосіб підтвердження."
            )

        if settlement == "membership":
            if membership_id is None:
                raise ValidationError(
                    "Потрібно вибрати абонемент."
                )
        elif membership_id is not None:
            raise ValidationError(
                "Абонемент передається лише "
                "для способу membership."
            )

        if settlement == "payment":
            if not isinstance(payment_successful, bool):
                raise ValidationError(
                    "Потрібно вказати результат імітації оплати."
                )
        elif payment_successful is not None:
            raise ValidationError(
                "Результат оплати передається лише "
                "для способу payment."
            )

        with transaction.atomic():
            try:
                booking = (
                    Booking.objects.select_for_update()
                    .get(pk=booking_id, user=user)
                )
            except (Booking.DoesNotExist, ValueError, TypeError):
                raise ValidationError(
                    "Власне бронювання не знайдено."
                )

            if booking.status == Booking.Status.CONFIRMED:
                return booking

            if booking.status == Booking.Status.CANCELLED:
                raise ValidationError(
                    "Скасоване бронювання не можна підтвердити."
                )

            if booking.starts_at <= timezone.now():
                raise ValidationError(
                    "Час початку бронювання вже настав."
                )

            if settlement == "payment":
                if not payment_successful:
                    raise ValidationError(
                        "Імітація оплати завершилася невдало. "
                        "Бронювання не підтверджено."
                    )

                if booking.total_price <= 0:
                    raise ValidationError(
                        "Безкоштовна послуга підтверджується "
                        "способом free."
                    )

                if booking.membership_id is not None:
                    raise ValidationError(
                        "Для цього бронювання вже "
                        "зазначено абонемент."
                    )

                successful_payment = booking.payments.filter(
                    status=Payment.Status.SUCCESS,
                ).first()

                if successful_payment is None:
                    payment = Payment(
                        booking=booking,
                        amount=booking.total_price,
                        status=Payment.Status.SUCCESS,
                    )
                    payment.full_clean()
                    payment.save()

            return BookingConfirmationService().confirm(
                booking_id=booking.pk,
                settlement=settlement,
                membership_id=membership_id,
            )