from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)

from catalog.models import (
    Hall,
    Section,
    SportsCenter,
    SportType,
    Trainer,
    TrainingSession,
)

from loyalty.models import (
    BonusTransaction,
    LoyaltyCard,
    Membership,
    MembershipPlan,
)

from .models import Booking, Payment
from .services import BookingService
from notifications.models import Notification


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

    def confirm_booking(self, data, booking=None, client=None):
        if booking is None:
            booking = self.own_booking
        if client is None:
            client = self.client

        return client.post(
            reverse(
                "bookings:booking-confirm",
                args=[booking.pk],
            ),
            data,
            format="json",
            **self.csrf_headers(client),
        )

    def create_membership(self, user, remaining_visits=2):
        plan = MembershipPlan.objects.create(
            name="Test hall membership",
            kind=MembershipPlan.Kind.MONTHLY,
            price=Decimal("1000.00"),
            validity_days=30,
            visit_limit=2,
            service_scope=MembershipPlan.ServiceScope.HALLS,
            sport_type=self.hall.sport_type,
        )
        return Membership.objects.create(
            user=user,
            plan=plan,
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=self.base_time + timedelta(days=10),
            remaining_visits=remaining_visits,
            status=Membership.Status.ACTIVE,
        )

    def test_checkout_payment_is_not_duplicated(self):
        data = {
            "settlement": "payment",
            "payment_successful": True,
        }

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                response = self.confirm_booking(data)
                self.assertEqual(response.status_code, 200)

        self.own_booking.refresh_from_db()
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.CONFIRMED,
        )

        payments = Payment.objects.filter(
            booking=self.own_booking
        )
        self.assertEqual(payments.count(), 1)
        self.assertEqual(
            payments.get().amount,
            Decimal("400.00"),
        )
        self.assertEqual(
            payments.get().status,
            Payment.Status.SUCCESS,
        )

        bonuses = BonusTransaction.objects.filter(
            booking=self.own_booking
        )
        self.assertEqual(bonuses.count(), 1)
        self.assertEqual(bonuses.get().points, 4)

        for kind in ("booking_confirmed", "bonus"):
            self.assertEqual(
                Notification.objects.filter(
                    booking=self.own_booking,
                    user=self.user,
                    kind=kind,
                ).count(),
                1,
            )

    def test_checkout_failed_payment_has_no_side_effects(self):
        response = self.confirm_booking({
            "settlement": "payment",
            "payment_successful": False,
        })

        self.assertEqual(response.status_code, 400)
        self.own_booking.refresh_from_db()
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.PENDING,
        )
        self.assertFalse(
            Payment.objects.filter(
                booking=self.own_booking
            ).exists()
        )
        self.assertFalse(
            BonusTransaction.objects.filter(
                booking=self.own_booking
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                booking=self.own_booking
            ).exists()
        )

    def test_checkout_is_only_available_to_owner(self):
        data = {
            "settlement": "payment",
            "payment_successful": True,
        }
        guest = APIClient(enforce_csrf_checks=True)
        response = self.confirm_booking(data, client=guest)
        self.assertEqual(response.status_code, 403)

        other_client = APIClient(enforce_csrf_checks=True)
        other_client.force_login(self.other_user)
        response = self.confirm_booking(
            data,
            client=other_client,
        )
        self.assertEqual(response.status_code, 404)

        self.own_booking.refresh_from_db()
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.PENDING,
        )
        self.assertFalse(
            Payment.objects.filter(
                booking=self.own_booking
            ).exists()
        )

    def test_checkout_requires_csrf(self):
        response = self.client.post(
            reverse(
                "bookings:booking-confirm",
                args=[self.own_booking.pk],
            ),
            {
                "settlement": "payment",
                "payment_successful": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Payment.objects.filter(
                booking=self.own_booking
            ).exists()
        )

    def test_checkout_rejects_invalid_parameters(self):
        cases = (
            {},
            {"settlement": "unknown"},
            {"settlement": "payment"},
            {"settlement": "membership"},
            {
                "settlement": "payment",
                "payment_successful": True,
                "membership_id": 1,
            },
            {
                "settlement": "free",
                "payment_successful": True,
            },
            {
                "settlement": "free",
                "membership_id": 1,
            },
        )

        for data in cases:
            with self.subTest(data=data):
                response = self.confirm_booking(data)
                self.assertEqual(response.status_code, 400)

        self.own_booking.refresh_from_db()
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.PENDING,
        )
        self.assertFalse(
            Payment.objects.filter(
                booking=self.own_booking
            ).exists()
        )

    def test_checkout_rejects_cancelled_and_past_bookings(self):
        self.own_booking.status = Booking.Status.CANCELLED
        self.own_booking.save(update_fields=["status"])

        response = self.confirm_booking({
            "settlement": "payment",
            "payment_successful": True,
        })
        self.assertEqual(response.status_code, 400)

        self.own_booking.status = Booking.Status.PENDING
        self.own_booking.starts_at = (
            timezone.now() - timedelta(hours=2)
        )
        self.own_booking.ends_at = (
            timezone.now() - timedelta(hours=1)
        )
        self.own_booking.save(
            update_fields=["status", "starts_at", "ends_at"]
        )

        response = self.confirm_booking({
            "settlement": "payment",
            "payment_successful": True,
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Payment.objects.filter(
                booking=self.own_booking
            ).exists()
        )

    def test_checkout_cannot_make_paid_booking_free(self):
        response = self.confirm_booking({
            "settlement": "free",
        })

        self.assertEqual(response.status_code, 400)
        self.own_booking.refresh_from_db()
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.PENDING,
        )
        self.assertEqual(
            self.own_booking.total_price,
            Decimal("400.00"),
        )

    def test_checkout_confirms_free_premium_swimming(self):
        card, _ = LoyaltyCard.objects.get_or_create(
            user=self.user,
        )
        card.category = "premium"
        card.save(update_fields=["category"])

        swimming = SportType.objects.create(
            name="Плавання"
        )
        pool = Hall.objects.create(
            center=self.hall.center,
            sport_type=swimming,
            name="Test pool",
            capacity=10,
            hourly_price=Decimal("800.00"),
        )
        booking = BookingService.create_hall_booking(
            user=self.user,
            hall_id=pool.pk,
            starts_at=self.base_time,
            ends_at=self.base_time + timedelta(hours=1),
        )
        self.assertEqual(
            booking.total_price,
            Decimal("0.00"),
        )

        response = self.confirm_booking(
            {"settlement": "free"},
            booking=booking,
        )

        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(
            booking.status,
            Booking.Status.CONFIRMED,
        )
        self.assertFalse(
            Payment.objects.filter(booking=booking).exists()
        )
        self.assertFalse(
            BonusTransaction.objects.filter(
                booking=booking
            ).exists()
        )
        self.assertEqual(
            Notification.objects.filter(
                booking=booking,
                kind="booking_confirmed",
            ).count(),
            1,
        )

    def test_checkout_membership_is_debited_once(self):
        membership = self.create_membership(self.user)
        data = {
            "settlement": "membership",
            "membership_id": membership.pk,
        }

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                response = self.confirm_booking(data)
                self.assertEqual(response.status_code, 200)

        membership.refresh_from_db()
        self.own_booking.refresh_from_db()

        self.assertEqual(membership.remaining_visits, 1)
        self.assertEqual(
            self.own_booking.membership_id,
            membership.pk,
        )
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.CONFIRMED,
        )
        self.assertFalse(
            Payment.objects.filter(
                booking=self.own_booking
            ).exists()
        )
        self.assertFalse(
            BonusTransaction.objects.filter(
                booking=self.own_booking
            ).exists()
        )
        self.assertEqual(
            Notification.objects.filter(
                booking=self.own_booking,
                kind="booking_confirmed",
            ).count(),
            1,
        )

    def test_checkout_rejects_other_users_membership(self):
        membership = self.create_membership(
            self.other_user
        )

        response = self.confirm_booking({
            "settlement": "membership",
            "membership_id": membership.pk,
        })

        self.assertEqual(response.status_code, 400)
        membership.refresh_from_db()
        self.own_booking.refresh_from_db()
        self.assertEqual(membership.remaining_visits, 2)
        self.assertIsNone(self.own_booking.membership_id)
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.PENDING,
        )

    def test_checkout_rejects_exhausted_membership(self):
        membership = self.create_membership(
            self.user,
            remaining_visits=0,
        )

        response = self.confirm_booking({
            "settlement": "membership",
            "membership_id": membership.pk,
        })

        self.assertEqual(response.status_code, 400)
        membership.refresh_from_db()
        self.own_booking.refresh_from_db()
        self.assertEqual(membership.remaining_visits, 0)
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.PENDING,
        )
        self.assertIsNone(self.own_booking.membership_id)

    def test_checkout_rolls_back_payment_on_confirmation_error(self):
        with patch(
            "bookings.services.BookingConfirmationService.confirm",
            side_effect=DjangoValidationError(
                "Test confirmation failure"
            ),
        ) as mocked_confirm:
            response = self.confirm_booking({
                "settlement": "payment",
                "payment_successful": True,
            })

        mocked_confirm.assert_called_once()
        self.assertEqual(response.status_code, 400)
        self.own_booking.refresh_from_db()
        self.assertEqual(
            self.own_booking.status,
            Booking.Status.PENDING,
        )
        self.assertFalse(
            Payment.objects.filter(
                booking=self.own_booking
            ).exists()
        )
        self.assertFalse(
            BonusTransaction.objects.filter(
                booking=self.own_booking
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                booking=self.own_booking
            ).exists()
        )