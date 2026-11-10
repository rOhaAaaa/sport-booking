from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from bookings.services import BookingService

from .models import (
    Hall,
    Section,
    SportsCenter,
    SportType,
    Trainer,
    TrainingSession,
)


User = get_user_model()


class TrainingScheduleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="schedule_admin",
            email="schedule@example.com",
            password="ScheduleTest!47River",
        )
        cls.user = User.objects.create_user(
            username="schedule_client",
            password="ClientTest!47River",
        )
        cls.other_user = User.objects.create_user(
            username="other_schedule_client",
            password="OtherTest!47River",
        )

        cls.center = SportsCenter.objects.create(
            name="Тестовий центр",
            address="Тестова адреса",
        )
        cls.sport = SportType.objects.create(name="Йога")

        cls.hall = Hall.objects.create(
            center=cls.center,
            sport_type=cls.sport,
            name="Перший зал",
            capacity=15,
            hourly_price=Decimal("400.00"),
        )
        cls.other_hall = Hall.objects.create(
            center=cls.center,
            sport_type=cls.sport,
            name="Другий зал",
            capacity=15,
            hourly_price=Decimal("400.00"),
        )

        cls.section = Section.objects.create(
            sport_type=cls.sport,
            name="Йога для початківців",
            skill_level=Section.SkillLevel.BEGINNER,
            age_category=Section.AgeCategory.ADULTS,
        )
        cls.other_section = Section.objects.create(
            sport_type=cls.sport,
            name="Інша секція йоги",
            skill_level=Section.SkillLevel.INTERMEDIATE,
            age_category=Section.AgeCategory.ADULTS,
        )

        cls.trainer = Trainer.objects.create(
            full_name="Перший тренер",
            specialization="Йога",
        )
        cls.other_trainer = Trainer.objects.create(
            full_name="Другий тренер",
            specialization="Йога",
        )

    def setUp(self):
        self.starts_at = (
            timezone.now() + timedelta(days=3)
        ).replace(
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
        )

        self.session = self.build_session()
        self.session.full_clean()
        self.session.save()

    def build_session(self, **overrides):
        data = {
            "section": self.section,
            "hall": self.hall,
            "trainer": self.trainer,
            "starts_at": self.starts_at,
            "ends_at": self.starts_at + timedelta(hours=1),
            "capacity": 10,
            "price": Decimal("150.00"),
        }
        data.update(overrides)
        return TrainingSession(**data)

    def assert_invalid(self, session, field):
        with self.assertRaises(ValidationError) as caught:
            session.full_clean()

        self.assertIn(field, caught.exception.message_dict)

    def create_rental(self):
        starts_at = self.starts_at + timedelta(days=1)
        return BookingService.create_hall_booking(
            user=self.user,
            hall_id=self.hall.pk,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

    def admin_payload(self, session):
        starts_at = timezone.localtime(session.starts_at)
        ends_at = timezone.localtime(session.ends_at)

        return {
            "section": session.section_id,
            "hall": session.hall_id,
            "trainer": session.trainer_id,
            "starts_at_0": starts_at.strftime("%Y-%m-%d"),
            "starts_at_1": starts_at.strftime("%H:%M:%S"),
            "ends_at_0": ends_at.strftime("%Y-%m-%d"),
            "ends_at_1": ends_at.strftime("%H:%M:%S"),
            "capacity": session.capacity,
            "price": str(session.price),
            "_save": "Зберегти",
        }

    def test_hall_rejects_different_overlap_shapes(self):
        cases = [
            (-30, 30),
            (30, 90),
            (0, 60),
            (-30, 90),
            (15, 45),
        ]

        for start_minutes, end_minutes in cases:
            with self.subTest(
                start=start_minutes,
                end=end_minutes,
            ):
                candidate = self.build_session(
                    trainer=self.other_trainer,
                    starts_at=(
                        self.starts_at
                        + timedelta(minutes=start_minutes)
                    ),
                    ends_at=(
                        self.starts_at
                        + timedelta(minutes=end_minutes)
                    ),
                )
                self.assert_invalid(candidate, "hall")

    def test_adjacent_sessions_are_allowed_on_both_sides(self):
        before = self.build_session(
            starts_at=self.starts_at - timedelta(hours=1),
            ends_at=self.starts_at,
        )
        before.full_clean()
        before.save()

        after = self.build_session(
            starts_at=self.session.ends_at,
            ends_at=self.session.ends_at + timedelta(hours=1),
        )
        after.full_clean()
        after.save()

        self.assertEqual(
            TrainingSession.objects.count(),
            3,
        )

    def test_parallel_sessions_with_different_resources_are_allowed(self):
        candidate = self.build_session(
            hall=self.other_hall,
            trainer=self.other_trainer,
        )
        candidate.full_clean()
        candidate.save()

        self.assertEqual(
            TrainingSession.objects.count(),
            2,
        )

    def test_trainer_cannot_teach_in_two_halls_at_once(self):
        candidate = self.build_session(
            hall=self.other_hall,
        )
        self.assert_invalid(candidate, "trainer")

    def test_pending_and_confirmed_rentals_block_session(self):
        rental = self.create_rental()

        for status in (
            Booking.Status.PENDING,
            Booking.Status.CONFIRMED,
        ):
            with self.subTest(status=status):
                Booking.objects.filter(pk=rental.pk).update(
                    status=status,
                )

                candidate = self.build_session(
                    starts_at=rental.starts_at,
                    ends_at=rental.ends_at,
                )
                self.assert_invalid(
                    candidate,
                    "starts_at",
                )

    def test_cancelled_rental_does_not_block_session(self):
        rental = self.create_rental()
        Booking.objects.filter(pk=rental.pk).update(
            status=Booking.Status.CANCELLED,
        )

        candidate = self.build_session(
            starts_at=rental.starts_at,
            ends_at=rental.ends_at,
        )
        candidate.full_clean()
        candidate.save()

        self.assertIsNotNone(candidate.pk)

    def test_existing_session_does_not_conflict_with_itself(self):
        self.session.full_clean()
        self.session.save()

        self.assertEqual(
            TrainingSession.objects.count(),
            1,
        )

    def test_editing_unbooked_session_detects_new_overlap(self):
        movable = self.build_session(
            starts_at=self.starts_at + timedelta(days=1),
            ends_at=(
                self.starts_at
                + timedelta(days=1, hours=1)
            ),
        )
        movable.full_clean()
        movable.save()
        original_start = movable.starts_at

        movable.starts_at = (
            self.starts_at + timedelta(minutes=30)
        )
        movable.ends_at = (
            self.starts_at + timedelta(minutes=90)
        )

        self.assert_invalid(movable, "hall")

        movable.refresh_from_db()
        self.assertEqual(
            movable.starts_at,
            original_start,
        )

    def test_booked_session_protects_section_hall_and_times(self):
        BookingService.create_session_booking(
            user=self.user,
            session_id=self.session.pk,
        )

        changes = {
            "section": self.other_section,
            "hall": self.other_hall,
            "starts_at": (
                self.session.starts_at
                + timedelta(minutes=10)
            ),
            "ends_at": (
                self.session.ends_at
                + timedelta(minutes=10)
            ),
        }

        for field, value in changes.items():
            with self.subTest(field=field):
                session = TrainingSession.objects.get(
                    pk=self.session.pk,
                )
                setattr(session, field, value)
                self.assert_invalid(session, field)

    def test_capacity_cannot_drop_below_active_bookings(self):
        BookingService.create_session_booking(
            user=self.user,
            session_id=self.session.pk,
        )
        other_booking = BookingService.create_session_booking(
            user=self.other_user,
            session_id=self.session.pk,
        )

        self.session.capacity = 1
        self.assert_invalid(self.session, "capacity")

        Booking.objects.filter(
            pk=other_booking.pk,
        ).update(
            status=Booking.Status.CANCELLED,
        )

        self.session.full_clean()
        self.session.save()

        self.assertEqual(
            self.session.capacity,
            1,
        )

    def test_admin_rejects_overlapping_session_without_saving(self):
        self.client.force_login(self.admin_user)
        candidate = self.build_session(
            trainer=self.other_trainer,
        )
        count_before = TrainingSession.objects.count()

        response = self.client.post(
            reverse("admin:catalog_trainingsession_add"),
            self.admin_payload(candidate),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "hall",
            response.context["adminform"].form.errors,
        )
        self.assertEqual(
            TrainingSession.objects.count(),
            count_before,
        )

    def test_admin_allows_adjacent_session(self):
        self.client.force_login(self.admin_user)
        candidate = self.build_session(
            starts_at=self.session.ends_at,
            ends_at=self.session.ends_at + timedelta(hours=1),
        )

        response = self.client.post(
            reverse("admin:catalog_trainingsession_add"),
            self.admin_payload(candidate),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TrainingSession.objects.filter(
                hall=self.hall,
                trainer=self.trainer,
                starts_at=candidate.starts_at,
                ends_at=candidate.ends_at,
            ).exists(),
        )