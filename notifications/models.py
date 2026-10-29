from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F


class Offer(models.Model):
    class TargetCategory(models.TextChoices):
        ALL = "all", "Усі клієнти"
        STANDARD = "standard", "Стандартна"
        PREMIUM = "premium", "Преміум"
        CORPORATE = "corporate", "Корпоративна"

    title = models.CharField(
        "Заголовок",
        max_length=200,
    )
    description = models.TextField(
        "Опис",
    )
    starts_at = models.DateTimeField(
        "Початок дії",
    )
    ends_at = models.DateTimeField(
        "Завершення дії",
    )
    target_card_category = models.CharField(
        "Категорія клієнтів",
        max_length=20,
        choices=TargetCategory.choices,
        default=TargetCategory.ALL,
    )

    class Meta:
        verbose_name = "Пропозиція"
        verbose_name_plural = "Пропозиції"
        ordering = ["-starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    ends_at__gt=F("starts_at"),
                ),
                name="offer_dates_valid",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValidationError({
                "ends_at": (
                    "Завершення дії пропозиції має бути "
                    "пізніше за початок."
                ),
            })

    def __str__(self):
        return self.title


class Notification(models.Model):
    class Kind(models.TextChoices):
        BOOKING_CONFIRMED = (
            "booking_confirmed",
            "Підтвердження бронювання",
        )
        REMINDER = "reminder", "Нагадування про заняття"
        BONUS = "bonus", "Нарахування бонусів"
        OFFER = "offer", "Пропозиція"
        INFO = "info", "Інформаційне повідомлення"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Отримувач",
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    kind = models.CharField(
        "Тип повідомлення",
        max_length=30,
        choices=Kind.choices,
        default=Kind.INFO,
    )
    message = models.TextField(
        "Текст повідомлення",
    )
    is_read = models.BooleanField(
        "Прочитано",
        default=False,
    )
    created_at = models.DateTimeField(
        "Створено",
        auto_now_add=True,
    )
    booking = models.ForeignKey(
        "bookings.Booking",
        verbose_name="Бронювання",
        on_delete=models.PROTECT,
        related_name="notifications",
        null=True,
        blank=True,
    )
    offer = models.ForeignKey(
        Offer,
        verbose_name="Пропозиція",
        on_delete=models.PROTECT,
        related_name="notifications",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Сповіщення"
        verbose_name_plural = "Сповіщення"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(booking__isnull=True)
                    | models.Q(offer__isnull=True)
                ),
                name="notification_at_most_one_link",
            ),
            models.UniqueConstraint(
                fields=["booking"],
                condition=models.Q(
                    kind="reminder",
                    booking__isnull=False,
                ),
                name="unique_booking_reminder",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        booking_kinds = {
            self.Kind.BOOKING_CONFIRMED,
            self.Kind.REMINDER,
            self.Kind.BONUS,
        }

        if self.booking_id and self.offer_id:
            errors["offer"] = (
                "Сповіщення може посилатися на бронювання "
                "або пропозицію, але не на обидва об’єкти."
            )

        if self.kind in booking_kinds:
            if not self.booking_id:
                errors["booking"] = (
                    "Для цього типу повідомлення "
                    "потрібно вибрати бронювання."
                )
            if self.offer_id:
                errors["offer"] = (
                    "Цей тип повідомлення не пов’язується "
                    "з пропозицією."
                )

        if self.kind == self.Kind.OFFER:
            if not self.offer_id:
                errors["offer"] = (
                    "Для цього типу повідомлення "
                    "потрібно вибрати пропозицію."
                )
            if self.booking_id:
                errors["booking"] = (
                    "Повідомлення про пропозицію "
                    "не пов’язується з бронюванням."
                )

        if self.kind == self.Kind.INFO:
            if self.booking_id or self.offer_id:
                errors["kind"] = (
                    "Для повідомлення з посиланням виберіть "
                    "відповідний спеціалізований тип."
                )

        if self.booking_id and self.user_id:
            if self.booking.user_id != self.user_id:
                errors["user"] = (
                    "Отримувач має бути власником бронювання."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.get_kind_display()} — {self.user}"