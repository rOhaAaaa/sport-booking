from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from bookings.models import Booking
from catalog.models import (
    Hall,
    Section,
    SportsCenter,
    SportType,
    Trainer,
    TrainingSession,
)
from notifications.models import Notification
from notifications.services import ReminderService


class ReminderServiceTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.clock = patch(
            "notifications.services.timezone.now",
            return_value=self.now,
        )
        self.clock.start()
        self.addCleanup(self.clock.stop)

        self.user = get_user_model().objects.create_user(
            username="reminder_user",
        )
        sport = SportType.objects.create(name="Йога")
        center = SportsCenter.objects.create(
            name="Тестовий центр",
            address="Тестова адреса",
        )
        self.hall = Hall.objects.create(
            center=center,
            sport_type=sport,
            name="Зал йоги",
            capacity=15,
            hourly_price=Decimal("400.00"),
        )
        self.section = Section.objects.create(
            sport_type=sport,
            name="Йога для початківців",
            skill_level="beginner",
            age_category="adults",
        )
        self.trainer = Trainer.objects.create(
            full_name="Тестовий тренер",
            specialization="Йога",
        )

    def create_booking(self, hours=12, status=None, hall_only=False):
        starts_at = self.now + timedelta(hours=hours)
        ends_at = starts_at + timedelta(hours=1)

        session = None
        if not hall_only:
            session = TrainingSession.objects.create(
                section=self.section,
                hall=self.hall,
                trainer=self.trainer,
                starts_at=starts_at,
                ends_at=ends_at,
                capacity=10,
                price=Decimal("150.00"),
            )

        return Booking.objects.create(
            user=self.user,
            hall=self.hall if hall_only else None,
            session=session,
            starts_at=starts_at,
            ends_at=ends_at,
            total_price=Decimal("150.00"),
            status=(
                Booking.Status.CONFIRMED
                if status is None
                else status
            ),
        )

    def test_creates_reminder_with_correct_details(self):
        booking = self.create_booking()

        self.assertEqual(
            ReminderService.create_upcoming_reminders(), 1
        )

        notification = Notification.objects.get(
            booking=booking,
            kind=Notification.Kind.REMINDER,
        )
        self.assertEqual(notification.user_id, self.user.pk)
        self.assertFalse(notification.is_read)
        self.assertIn(self.section.name, notification.message)
        self.assertIn(self.hall.name, notification.message)
        self.assertIn(
            timezone.localtime(booking.starts_at).strftime(
                "%d.%m.%Y о %H:%M"
            ),
            notification.message,
        )

    def test_repeated_run_does_not_create_duplicate(self):
        self.create_booking()

        self.assertEqual(
            ReminderService.create_upcoming_reminders(), 1
        )
        self.assertEqual(
            ReminderService.create_upcoming_reminders(), 0
        )
        self.assertEqual(Notification.objects.count(), 1)

    def test_time_window_boundaries(self):
        for hours in (-2, 0, 24, 25):
            self.create_booking(hours=hours)

        self.assertEqual(
            ReminderService.create_upcoming_reminders(), 1
        )

    def test_pending_and_cancelled_are_excluded(self):
        self.create_booking(status=Booking.Status.PENDING)
        self.create_booking(status=Booking.Status.CANCELLED)

        self.assertEqual(
            ReminderService.create_upcoming_reminders(), 0
        )

    def test_inactive_user_is_excluded(self):
        self.create_booking()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        self.assertEqual(
            ReminderService.create_upcoming_reminders(), 0
        )

    def test_hall_rental_is_excluded(self):
        self.create_booking(hall_only=True)

        self.assertEqual(
            ReminderService.create_upcoming_reminders(), 0
        )

    def test_invalid_hours_are_rejected(self):
        for hours in (0, -1, 721, True, "24", 1.5):
            with self.subTest(hours=hours):
                with self.assertRaises(ValueError):
                    ReminderService.create_upcoming_reminders(
                        hours=hours
                    )

    def test_database_rejects_duplicate_reminder(self):
        booking = self.create_booking()
        ReminderService.create_upcoming_reminders()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(
                    user=self.user,
                    booking=booking,
                    kind=Notification.Kind.REMINDER,
                    message="Повторне нагадування",
                )

    def test_command_supports_custom_window_and_repeat(self):
        self.create_booking(hours=48)
        output = StringIO()

        call_command(
            "send_training_reminders",
            hours=72,
            stdout=output,
        )
        self.assertIn(
            "Створено нагадувань: 1", output.getvalue()
        )

        output = StringIO()
        call_command(
            "send_training_reminders",
            hours=72,
            stdout=output,
        )
        self.assertIn(
            "Створено нагадувань: 0", output.getvalue()
        )

    def test_command_rejects_invalid_hours(self):
        with self.assertRaises(CommandError):
            call_command("send_training_reminders", hours=0)