from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F
from django.utils import timezone


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Очікує підтвердження"
        CONFIRMED = "confirmed", "Підтверджено"
        CANCELLED = "cancelled", "Скасовано"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Користувач",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    hall = models.ForeignKey(
        "catalog.Hall",
        verbose_name="Зал для оренди",
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
    )
    session = models.ForeignKey(
        "catalog.TrainingSession",
        verbose_name="Заняття",
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
    )
    membership = models.ForeignKey(
        "loyalty.Membership",
        verbose_name="Використаний абонемент",
        on_delete=models.PROTECT,
        related_name="bookings",
        null=True,
        blank=True,
    )
    starts_at = models.DateTimeField(
        "Початок",
    )
    ends_at = models.DateTimeField(
        "Завершення",
    )
    total_price = models.DecimalField(
        "Вартість, грн",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(
        "Створено",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Бронювання"
        verbose_name_plural = "Бронювання"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        hall__isnull=False,
                        session__isnull=True,
                    )
                    | models.Q(
                        hall__isnull=True,
                        session__isnull=False,
                    )
                ),
                name="booking_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    ends_at__gt=F("starts_at"),
                ),
                name="booking_dates_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(total_price__gte=0),
                name="booking_price_nonnegative",
            ),
            models.UniqueConstraint(
                fields=["user", "session"],
                condition=models.Q(
                    status__in=["pending", "confirmed"],
                    session__isnull=False,
                ),
                name="booking_unique_active_session",
                violation_error_message=(
                    "Користувач уже має активне бронювання "
                    "на це заняття."
                ),
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if bool(self.hall_id) == bool(self.session_id):
            errors["hall"] = (
                "Оберіть або зал для оренди, або заняття — "
                "рівно один із цих варіантів."
            )

        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            errors["ends_at"] = (
                "Завершення має бути пізніше за початок."
            )

        if (
            self._state.adding
            and self.starts_at is not None
            and self.starts_at <= timezone.now()
        ):
            errors["starts_at"] = (
                "Нове бронювання потрібно створювати "
                "на майбутній час."
            )

        if self.session_id:
            session = self.session

            if (
                self.starts_at is not None
                and self.starts_at != session.starts_at
            ):
                errors["starts_at"] = (
                    "Початок бронювання має відповідати "
                    "початку заняття."
                )

            if (
                self.ends_at is not None
                and self.ends_at != session.ends_at
            ):
                errors["ends_at"] = (
                    "Завершення бронювання має відповідати "
                    "завершенню заняття."
                )

        if self.membership_id and self.user_id:
            if self.membership.user_id != self.user_id:
                errors["membership"] = (
                    "Абонемент має належати користувачу, "
                    "який здійснює бронювання."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Бронювання №{self.pk} — {self.user}"

class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Очікує оброблення"
        SUCCESS = "success", "Успішна"
        FAILED = "failed", "Невдала"

    booking = models.ForeignKey(
        Booking,
        verbose_name="Бронювання",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(
        "Сума, грн",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(
        "Створено",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Оплата"
        verbose_name_plural = "Оплати"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_amount_positive",
            ),
            models.UniqueConstraint(
                fields=["booking"],
                condition=models.Q(status="success"),
                name="payment_one_success_per_booking",
                violation_error_message=(
                    "Це бронювання вже має успішну оплату."
                ),
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.booking_id:
            booking = self.booking

            if (
                self.amount is not None
                and self.amount != booking.total_price
            ):
                errors["amount"] = (
                    "Сума оплати має дорівнювати "
                    "вартості бронювання."
                )

            if (
                self.status == self.Status.SUCCESS
                and booking.status == Booking.Status.CANCELLED
            ):
                errors["status"] = (
                    "Не можна успішно оплатити "
                    "скасоване бронювання."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"Оплата №{self.pk} — "
            f"бронювання №{self.booking_id}"
        )