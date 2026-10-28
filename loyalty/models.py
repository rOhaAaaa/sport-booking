from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F


class MembershipPlan(models.Model):
    class Kind(models.TextChoices):
        SINGLE = "single", "Разовий"
        MONTHLY = "monthly", "Місячний"
        CORPORATE = "corporate", "Корпоративний"

    class ServiceScope(models.TextChoices):
        SESSIONS = "sessions", "Заняття секцій"
        HALLS = "halls", "Оренда залів"
        BOTH = "both", "Заняття та оренда залів"

    name = models.CharField(
        "Назва",
        max_length=150,
    )
    kind = models.CharField(
        "Тип абонемента",
        max_length=20,
        choices=Kind.choices,
    )
    price = models.DecimalField(
        "Вартість, грн",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    validity_days = models.PositiveIntegerField(
        "Строк дії, днів",
        default=30,
        validators=[MinValueValidator(1)],
    )
    visit_limit = models.PositiveIntegerField(
        "Ліміт використань",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Залиште порожнім для необмеженої кількості.",
    )
    service_scope = models.CharField(
        "Доступні послуги",
        max_length=20,
        choices=ServiceScope.choices,
        default=ServiceScope.SESSIONS,
    )
    sport_type = models.ForeignKey(
        "catalog.SportType",
        verbose_name="Вид спорту",
        on_delete=models.PROTECT,
        related_name="membership_plans",
        null=True,
        blank=True,
        help_text="Залиште порожнім, якщо доступні всі види спорту.",
    )

    class Meta:
        verbose_name = "Тариф абонемента"
        verbose_name_plural = "Тарифи абонементів"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="plan_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(validity_days__gte=1),
                name="plan_validity_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(visit_limit__isnull=True)
                    | models.Q(visit_limit__gte=1)
                ),
                name="plan_visit_limit_positive",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(kind="single")
                    | (
                        models.Q(visit_limit__isnull=False)
                        & models.Q(visit_limit=1)
                    )
                ),
                name="single_plan_one_use",
            ),
        ]

    def clean(self):
        super().clean()

        if self.kind == self.Kind.SINGLE and self.visit_limit != 1:
            raise ValidationError({
                "visit_limit": (
                    "Для разового абонемента ліміт використань "
                    "має дорівнювати 1."
                ),
            })

    def __str__(self):
        return self.name


class LoyaltyCard(models.Model):
    class Category(models.TextChoices):
        STANDARD = "standard", "Стандартна"
        PREMIUM = "premium", "Преміум"
        CORPORATE = "corporate", "Корпоративна"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Користувач",
        on_delete=models.PROTECT,
        related_name="loyalty_card",
    )
    category = models.CharField(
        "Категорія картки",
        max_length=20,
        choices=Category.choices,
        default=Category.STANDARD,
    )

    class Meta:
        verbose_name = "Картка лояльності"
        verbose_name_plural = "Картки лояльності"

    def __str__(self):
        return f"{self.user} — {self.get_category_display()}"
    
class Membership(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активний"
        CANCELLED = "cancelled", "Скасований"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Користувач",
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    plan = models.ForeignKey(
        MembershipPlan,
        verbose_name="Тариф",
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    valid_from = models.DateTimeField(
        "Початок дії",
    )
    valid_until = models.DateTimeField(
        "Завершення дії",
    )
    remaining_visits = models.PositiveIntegerField(
        "Залишок використань",
        null=True,
        blank=True,
        help_text=(
            "Для обмеженого тарифу вкажіть залишок використань. "
            "Для необмеженого залиште порожнім."
        ),
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        verbose_name = "Абонемент користувача"
        verbose_name_plural = "Абонементи користувачів"
        ordering = ["-valid_from"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    valid_until__gt=F("valid_from"),
                ),
                name="membership_dates_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(remaining_visits__isnull=True)
                    | models.Q(remaining_visits__gte=0)
                ),
                name="membership_visits_nonnegative",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            errors["valid_until"] = (
                "Завершення дії має бути пізніше за початок."
            )

        if self.plan_id:
            limit = self.plan.visit_limit

            if limit is None:
                if self.remaining_visits is not None:
                    errors["remaining_visits"] = (
                        "Для необмеженого тарифу залиште "
                        "це поле порожнім."
                    )
            elif self.remaining_visits is None:
                errors["remaining_visits"] = (
                    "Для цього тарифу потрібно вказати "
                    "залишок використань."
                )
            elif self.remaining_visits > limit:
                errors["remaining_visits"] = (
                    "Залишок використань не може перевищувати "
                    "ліміт тарифу."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.user} — {self.plan}"    

class BonusTransaction(models.Model):
    card = models.ForeignKey(
        LoyaltyCard,
        verbose_name="Картка лояльності",
        on_delete=models.PROTECT,
        related_name="bonus_transactions",
    )
    booking = models.OneToOneField(
        "bookings.Booking",
        verbose_name="Бронювання",
        on_delete=models.PROTECT,
        related_name="bonus_transaction",
    )
    points = models.PositiveIntegerField(
        "Кількість балів",
        validators=[MinValueValidator(1)],
    )
    created_at = models.DateTimeField(
        "Створено",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Нарахування бонусів"
        verbose_name_plural = "Нарахування бонусів"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(points__gte=1),
                name="bonus_points_positive",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.booking_id:
            booking = self.booking

            if booking.status != "confirmed":
                errors["booking"] = (
                    "Бонуси можна нараховувати лише "
                    "за підтверджене бронювання."
                )

            if self.card_id:
                if self.card.user_id != booking.user_id:
                    errors["card"] = (
                        "Картка має належати користувачу, "
                        "який здійснив бронювання."
                    )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"+{self.points} балів — "
            f"бронювання №{self.booking_id}"
        )