from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.apps import apps


class SportsCenter(models.Model):
    name = models.CharField("Назва", max_length=150)
    address = models.CharField("Адреса", max_length=255)

    class Meta:
        verbose_name = "Спортивний центр"
        verbose_name_plural = "Спортивні центри"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SportType(models.Model):
    name = models.CharField(
        "Вид спорту",
        max_length=100,
        unique=True,
    )

    class Meta:
        verbose_name = "Вид спорту"
        verbose_name_plural = "Види спорту"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Hall(models.Model):
    center = models.ForeignKey(
        SportsCenter,
        on_delete=models.PROTECT,
        related_name="halls",
        verbose_name="Спортивний центр",
    )
    sport_type = models.ForeignKey(
        SportType,
        on_delete=models.PROTECT,
        related_name="halls",
        verbose_name="Вид спорту",
    )
    name = models.CharField("Назва", max_length=150)
    capacity = models.PositiveIntegerField(
        "Місткість",
        validators=[MinValueValidator(1)],
    )
    hourly_price = models.DecimalField(
        "Вартість години, грн",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        verbose_name = "Спортивний зал"
        verbose_name_plural = "Спортивні зали"
        ordering = ["center__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["center", "name"],
                name="unique_hall_name_per_center",
            ),
            models.CheckConstraint(
                condition=Q(capacity__gte=1),
                name="hall_capacity_positive",
            ),
            models.CheckConstraint(
                condition=Q(hourly_price__gte=0),
                name="hall_price_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.center.name}: {self.name}"


class Section(models.Model):
    class SkillLevel(models.TextChoices):
        BEGINNER = "beginner", "Початковий"
        INTERMEDIATE = "intermediate", "Середній"
        ADVANCED = "advanced", "Високий"

    class AgeCategory(models.TextChoices):
        CHILDREN = "children", "Діти"
        TEENS = "teens", "Підлітки"
        ADULTS = "adults", "Дорослі"
        ALL = "all", "Усі вікові категорії"

    sport_type = models.ForeignKey(
        SportType,
        on_delete=models.PROTECT,
        related_name="sections",
        verbose_name="Вид спорту",
    )
    name = models.CharField("Назва", max_length=150)
    skill_level = models.CharField(
        "Рівень підготовки",
        max_length=20,
        choices=SkillLevel.choices,
    )
    age_category = models.CharField(
        "Вікова категорія",
        max_length=20,
        choices=AgeCategory.choices,
    )

    class Meta:
        verbose_name = "Спортивна секція"
        verbose_name_plural = "Спортивні секції"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Trainer(models.Model):
    full_name = models.CharField("ПІБ", max_length=150)
    specialization = models.CharField(
        "Спеціалізація",
        max_length=200,
    )

    class Meta:
        verbose_name = "Тренер"
        verbose_name_plural = "Тренери"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class TrainingSession(models.Model):
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="sessions",
        verbose_name="Секція",
    )
    hall = models.ForeignKey(
        Hall,
        on_delete=models.PROTECT,
        related_name="sessions",
        verbose_name="Зал",
    )
    trainer = models.ForeignKey(
        Trainer,
        on_delete=models.PROTECT,
        related_name="sessions",
        verbose_name="Тренер",
    )
    starts_at = models.DateTimeField("Початок")
    ends_at = models.DateTimeField("Завершення")
    capacity = models.PositiveIntegerField(
        "Кількість місць",
        validators=[MinValueValidator(1)],
    )
    price = models.DecimalField(
        "Ціна одного місця, грн",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        verbose_name = "Заняття"
        verbose_name_plural = "Заняття"
        ordering = ["starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="session_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(capacity__gte=1),
                name="session_capacity_positive",
            ),
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="session_price_nonnegative",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        valid_period = (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at > self.starts_at
        )

        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            errors["ends_at"] = (
                "Завершення має бути пізніше за початок."
            )

        if self.hall_id and self.capacity is not None:
            if self.capacity > self.hall.capacity:
                errors["capacity"] = (
                    "Кількість місць перевищує місткість залу."
                )

        if self.hall_id and self.section_id:
            if (
                self.hall.sport_type_id
                != self.section.sport_type_id
            ):
                errors["hall"] = (
                    "Вид спорту залу має відповідати "
                    "виду спорту секції."
                )

        Booking = apps.get_model("bookings", "Booking")
        active_statuses = (
            Booking.Status.PENDING,
            Booking.Status.CONFIRMED,
        )

        if valid_period:
            overlapping_sessions = (
                TrainingSession.objects.filter(
                    starts_at__lt=self.ends_at,
                    ends_at__gt=self.starts_at,
                )
                .exclude(pk=self.pk)
            )

            if self.hall_id:
                if overlapping_sessions.filter(
                    hall_id=self.hall_id,
                ).exists():
                    errors["hall"] = (
                        "У цьому залі вже заплановано "
                        "інше заняття на вибраний час."
                    )

                if Booking.objects.filter(
                    hall_id=self.hall_id,
                    status__in=active_statuses,
                    starts_at__lt=self.ends_at,
                    ends_at__gt=self.starts_at,
                ).exists():
                    errors["starts_at"] = (
                        "Вибраний час перетинається "
                        "з активною орендою цього залу."
                    )

            if self.trainer_id:
                if overlapping_sessions.filter(
                    trainer_id=self.trainer_id,
                ).exists():
                    errors["trainer"] = (
                        "Тренер уже проводить інше заняття "
                        "на вибраний час."
                    )

        if not self._state.adding and self.pk is not None:
            bookings = Booking.objects.filter(
                session_id=self.pk,
            )

            active_count = bookings.filter(
                status__in=active_statuses,
            ).count()

            if (
                self.capacity is not None
                and self.capacity < active_count
            ):
                errors["capacity"] = (
                    "Кількість місць не може бути меншою "
                    "за кількість активних бронювань "
                    f"({active_count})."
                )

            if bookings.exists():
                original = (
                    TrainingSession.objects.filter(pk=self.pk)
                    .values(
                        "section_id",
                        "hall_id",
                        "starts_at",
                        "ends_at",
                    )
                    .first()
                )

                if original is not None:
                    protected_fields = {
                        "section_id": "section",
                        "hall_id": "hall",
                        "starts_at": "starts_at",
                        "ends_at": "ends_at",
                    }

                    for attribute, field in protected_fields.items():
                        if (
                            getattr(self, attribute)
                            != original[attribute]
                        ):
                            errors[field] = (
                                "На це заняття вже є бронювання. "
                                "Змінювати секцію, зал або час "
                                "такого заняття не можна."
                            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.section.name} — {self.starts_at}"