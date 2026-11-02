from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from catalog.models import (
    Hall,
    Section,
    SportsCenter,
    SportType,
    Trainer,
    TrainingSession,
)

from .models import Booking
from .services import BookingService


User = get_user_model()


class BookingAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="booking_client",
            password="SportDemo!47River",
        )
        cls.other_user = User.objects.create_user(
            username="other_booking_client",
            password="SportDemo!47River",
        )

        center = SportsCenter.objects.create(
            name="Test center",
            address="Test address",
        )
        sport_type = SportType.objects.create(name="Йога")

        cls.hall = Hall.objects.create(
            center=center,
            sport_type=sport_type,
            name="Test hall",
            capacity=10,
            hourly_price=Decimal("400.00"),
        )
        section = Section.objects.create(
            sport_type=sport_type,
            name="Test section",
            skill_level="beginner",
            age_category="adults",
        )
        trainer = Trainer.objects.create(
            full_name="Test Trainer",
            specialization="Yoga",
        )

        cls.base_time = (
            timezone.now() + timedelta(days=1)
        ).replace(minute=0, second=0, microsecond=0)

        cls.session = TrainingSession.objects.create(
            section=section,
            hall=cls.hall,
            trainer=trainer,
            starts_at=cls.base_time + timedelta(days=2),
            ends_at=cls.base_time + timedelta(days=2, hours=1),
            capacity=2,
            price=Decimal("150.00"),
        )

        cls.own_booking = BookingService.create_hall_booking(
            user=cls.user,
            hall_id=cls.hall.pk,
            starts_at=cls.base_time,
            ends_at=cls.base_time + timedelta(hours=1),
        )
        cls.other_booking = BookingService.create_hall_booking(
            user=cls.other_user,
            hall_id=cls.hall.pk,
            starts_at=cls.base_time + timedelta(days=1),
            ends_at=cls.base_time + timedelta(days=1, hours=1),
        )

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def csrf_headers(self, client=None):
        if client is None:
            client = self.client

        response = client.get(reverse("accounts:csrf"))
        self.assertEqual(response.status_code, 200)
        return {
            "HTTP_X_CSRFTOKEN": response.data["csrfToken"],
        }

    def hall_data(self, **changes):
        data = {
            "hall_id": self.hall.pk,
            "starts_at": (
                self.base_time + timedelta(days=3)
            ).isoformat(),
            "ends_at": (
                self.base_time + timedelta(days=3, hours=1)
            ).isoformat(),
        }
        data.update(changes)
        return data

    def post_hall(self, data=None):
        return self.client.post(
            reverse("bookings:booking-create-hall"),
            self.hall_data() if data is None else data,
            format="json",
            **self.csrf_headers(),
        )

    def post_session(self, session_id=None):
        return self.client.post(
            reverse("bookings:booking-create-session"),
            {
                "session_id": (
                    self.session.pk
                    if session_id is None
                    else session_id
                ),
            },
            format="json",
            **self.csrf_headers(),
        )

    def test_guest_cannot_access_bookings(self):
        guest = APIClient(enforce_csrf_checks=True)
        headers = self.csrf_headers(guest)
        count_before = Booking.objects.count()

        for url in (
            reverse("bookings:booking-list"),
            reverse(
                "bookings:booking-detail",
                args=[self.own_booking.pk],
            ),
        ):
            with self.subTest(url=url):
                response = guest.get(url)
                self.assertEqual(response.status_code, 403)

        for route, data in (
            (
                "bookings:booking-create-hall",
                self.hall_data(),
            ),
            (
                "bookings:booking-create-session",
                {"session_id": self.session.pk},
            ),
        ):
            with self.subTest(route=route):
                response = guest.post(
                    reverse(route),
                    data,
                    format="json",
                    **headers,
                )
                self.assertEqual(response.status_code, 403)

        self.assertEqual(
            Booking.objects.count(),
            count_before,
        )

    def test_list_contains_only_own_bookings(self):
        response = self.client.get(
            reverse("bookings:booking-list")
        )

        self.assertEqual(response.status_code, 200)
        data = response.data
        if isinstance(data, dict):
            data = data["results"]

        self.assertEqual(
            {item["id"] for item in data},
            {self.own_booking.pk},
        )

    def test_detail_hides_other_users_booking(self):
        own_response = self.client.get(
            reverse(
                "bookings:booking-detail",
                args=[self.own_booking.pk],
            )
        )
        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(
            own_response.data["id"],
            self.own_booking.pk,
        )

        other_response = self.client.get(
            reverse(
                "bookings:booking-detail",
                args=[self.other_booking.pk],
            )
        )
        self.assertEqual(other_response.status_code, 404)

    def test_hall_booking_uses_session_owner_and_server_price(self):
        response = self.post_hall(
            self.hall_data(
                user=self.other_user.pk,
                user_id=self.other_user.pk,
                total_price="0.01",
                status="confirmed",
                membership=self.other_user.pk,
            )
        )

        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(pk=response.data["id"])
        self.assertEqual(booking.user_id, self.user.pk)
        self.assertEqual(booking.hall_id, self.hall.pk)
        self.assertIsNone(booking.session_id)
        self.assertIsNone(booking.membership_id)
        self.assertEqual(
            booking.total_price,
            Decimal("400.00"),
        )
        self.assertEqual(
            booking.status,
            Booking.Status.PENDING,
        )

    def test_session_booking_uses_session_dates_and_price(self):
        response = self.post_session()

        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(pk=response.data["id"])
        self.assertEqual(booking.user_id, self.user.pk)
        self.assertEqual(booking.session_id, self.session.pk)
        self.assertIsNone(booking.hall_id)
        self.assertEqual(
            booking.starts_at,
            self.session.starts_at,
        )
        self.assertEqual(
            booking.ends_at,
            self.session.ends_at,
        )
        self.assertEqual(
            booking.total_price,
            Decimal("150.00"),
        )
        self.assertEqual(
            booking.status,
            Booking.Status.PENDING,
        )

    def test_duplicate_session_booking_is_rejected(self):
        first_response = self.post_session()
        self.assertEqual(first_response.status_code, 201)
        count_before = Booking.objects.count()

        response = self.post_session()

        self.assertEqual(response.status_code, 400)
        self.assertIn("non_field_errors", response.data)
        self.assertEqual(
            Booking.objects.count(),
            count_before,
        )

    def test_overlapping_hall_booking_is_rejected(self):
        count_before = Booking.objects.count()
        response = self.post_hall(
            self.hall_data(
                starts_at=self.own_booking.starts_at.isoformat(),
                ends_at=self.own_booking.ends_at.isoformat(),
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("non_field_errors", response.data)
        self.assertEqual(
            Booking.objects.count(),
            count_before,
        )

    def test_invalid_periods_are_rejected(self):
        count_before = Booking.objects.count()

        periods = (
            (
                self.base_time + timedelta(hours=2),
                self.base_time + timedelta(hours=1),
            ),
            (
                self.base_time,
                self.base_time,
            ),
            (
                timezone.now() - timedelta(hours=2),
                timezone.now() - timedelta(hours=1),
            ),
        )

        for starts_at, ends_at in periods:
            with self.subTest(
                starts_at=starts_at,
                ends_at=ends_at,
            ):
                response = self.post_hall(
                    self.hall_data(
                        starts_at=starts_at.isoformat(),
                        ends_at=ends_at.isoformat(),
                    )
                )
                self.assertEqual(response.status_code, 400)

        self.assertEqual(
            Booking.objects.count(),
            count_before,
        )

    def test_missing_targets_are_rejected(self):
        count_before = Booking.objects.count()

        hall_response = self.post_hall(
            self.hall_data(hall_id=999999)
        )
        session_response = self.post_session(
            session_id=999999
        )

        self.assertEqual(hall_response.status_code, 400)
        self.assertEqual(session_response.status_code, 400)
        self.assertEqual(
            Booking.objects.count(),
            count_before,
        )

    def test_full_session_is_rejected(self):
        self.session.capacity = 1
        self.session.save(update_fields=["capacity"])

        BookingService.create_session_booking(
            user=self.other_user,
            session_id=self.session.pk,
        )
        count_before = Booking.objects.count()

        response = self.post_session()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            Booking.objects.count(),
            count_before,
        )

    def test_creation_requires_csrf(self):
        count_before = Booking.objects.count()

        for route, data in (
            (
                "bookings:booking-create-hall",
                self.hall_data(),
            ),
            (
                "bookings:booking-create-session",
                {"session_id": self.session.pk},
            ),
        ):
            with self.subTest(route=route):
                response = self.client.post(
                    reverse(route),
                    data,
                    format="json",
                )
                self.assertEqual(response.status_code, 403)

        self.assertEqual(
            Booking.objects.count(),
            count_before,
        )

    def test_direct_changes_and_deletion_are_not_allowed(self):
        url = reverse(
            "bookings:booking-detail",
            args=[self.own_booking.pk],
        )
        headers = self.csrf_headers()

        for method in ("patch", "put", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    url,
                    {"status": "confirmed"},
                    format="json",
                    **headers,
                )
                self.assertEqual(response.status_code, 405)

        self.own_booking.refresh_from_db()
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.PENDING,
        )