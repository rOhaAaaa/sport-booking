from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Hall, SportsCenter, SportType
from loyalty.models import (
    BonusTransaction,
    LoyaltyCard,
    MembershipPlan,
)
from loyalty.services import MembershipService
from notifications.models import Notification

from .models import Booking, Payment
from .services import BookingService


User = get_user_model()


class BookingAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="admin_test",
            email="admin@example.com",
            password="AdminTest!47River",
        )
        cls.user = User.objects.create_user(
            username="booking_client",
            password="ClientTest!47River",
        )
        cls.other_user = User.objects.create_user(
            username="other_client",
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
            name="Тестовий зал",
            capacity=15,
            hourly_price=Decimal("400.00"),
        )
        cls.plan = MembershipPlan.objects.create(
            name="Разова оренда",
            kind=MembershipPlan.Kind.SINGLE,
            price=Decimal("400.00"),
            validity_days=7,
            visit_limit=1,
            service_scope=MembershipPlan.ServiceScope.HALLS,
            sport_type=cls.sport,
        )

    def setUp(self):
        self.client.force_login(self.admin_user)
        self.list_url = reverse(
            "admin:bookings_booking_changelist",
        )
        self.starts_at = (
            timezone.now() + timedelta(days=2)
        ).replace(microsecond=0)

    def create_booking(self, day_offset=0, hall=None):
        starts_at = self.starts_at + timedelta(
            days=day_offset,
        )
        return BookingService.create_hall_booking(
            user=self.user,
            hall_id=(hall or self.hall).pk,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

    def run_action(self, action, *bookings):
        return self.client.post(
            self.list_url,
            {
                "action": action,
                "_selected_action": [
                    str(booking.pk)
                    for booking in bookings
                ],
                "index": "0",
                "select_across": "0",
            },
            follow=True,
        )

    def change_url(self, booking):
        return reverse(
            "admin:bookings_booking_change",
            args=[booking.pk],
        )

    def test_payment_action_creates_results_once_for_client(self):
        booking = self.create_booking()

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                response = self.run_action(
                    "confirm_with_payment",
                    booking,
                )
                self.assertEqual(response.status_code, 200)

                booking.refresh_from_db()
                self.assertEqual(
                    booking.status,
                    Booking.Status.CONFIRMED,
                )

                payment = Payment.objects.get(
                    booking=booking,
                )
                self.assertEqual(
                    payment.status,
                    Payment.Status.SUCCESS,
                )
                self.assertEqual(
                    payment.amount,
                    Decimal("400.00"),
                )

                bonus = BonusTransaction.objects.get(
                    booking=booking,
                )
                self.assertEqual(bonus.points, 4)
                self.assertEqual(
                    bonus.card.user_id,
                    self.user.pk,
                )

                notifications = Notification.objects.filter(
                    booking=booking,
                )
                self.assertEqual(notifications.count(), 2)
                self.assertEqual(
                    set(notifications.values_list(
                        "kind",
                        flat=True,
                    )),
                    {
                        Notification.Kind.BONUS,
                        Notification.Kind.BOOKING_CONFIRMED,
                    },
                )
                self.assertFalse(
                    notifications.exclude(
                        user=self.user,
                    ).exists(),
                )

    def test_membership_selection_and_action_debit_once(self):
        booking = self.create_booking()
        membership = MembershipService.purchase(
            user=self.user,
            plan_id=self.plan.pk,
            payment_successful=True,
        )

        response = self.client.post(
            self.change_url(booking),
            {
                "membership": membership.pk,
                "_save": "Зберегти",
            },
        )
        self.assertEqual(response.status_code, 302)

        booking.refresh_from_db()
        membership.refresh_from_db()

        self.assertEqual(
            booking.status,
            Booking.Status.PENDING,
        )
        self.assertEqual(
            booking.membership_id,
            membership.pk,
        )
        self.assertEqual(membership.remaining_visits, 1)
        self.assertFalse(
            Notification.objects.filter(
                booking=booking,
            ).exists(),
        )

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                response = self.run_action(
                    "confirm_with_membership",
                    booking,
                )
                self.assertEqual(response.status_code, 200)

                booking.refresh_from_db()
                membership.refresh_from_db()

                self.assertEqual(
                    booking.status,
                    Booking.Status.CONFIRMED,
                )
                self.assertEqual(
                    membership.remaining_visits,
                    0,
                )
                self.assertFalse(
                    Payment.objects.filter(
                        booking=booking,
                    ).exists(),
                )
                self.assertFalse(
                    BonusTransaction.objects.filter(
                        booking=booking,
                    ).exists(),
                )
                notification = Notification.objects.get(
                    booking=booking,
                )
                self.assertEqual(
                    notification.kind,
                    Notification.Kind.BOOKING_CONFIRMED,
                )
                self.assertEqual(
                    notification.user_id,
                    self.user.pk,
                )

    def test_free_action_checks_price_and_premium_benefit(self):
        paid_booking = self.create_booking()

        response = self.run_action(
            "confirm_free",
            paid_booking,
        )
        self.assertEqual(response.status_code, 200)
        paid_booking.refresh_from_db()
        self.assertEqual(
            paid_booking.status,
            Booking.Status.PENDING,
        )
        self.assertFalse(
            Notification.objects.filter(
                booking=paid_booking,
            ).exists(),
        )

        swimming = SportType.objects.create(
            name="Плавання",
        )
        pool = Hall.objects.create(
            center=self.center,
            sport_type=swimming,
            name="Басейн",
            capacity=12,
            hourly_price=Decimal("800.00"),
        )
        LoyaltyCard.objects.update_or_create(
            user=self.user,
            defaults={
                "category": LoyaltyCard.Category.PREMIUM,
            },
        )

        free_booking = self.create_booking(hall=pool)
        self.assertEqual(
            free_booking.total_price,
            Decimal("0.00"),
        )

        response = self.run_action(
            "confirm_free",
            free_booking,
        )
        self.assertEqual(response.status_code, 200)

        free_booking.refresh_from_db()
        self.assertEqual(
            free_booking.status,
            Booking.Status.CONFIRMED,
        )
        self.assertFalse(
            Payment.objects.filter(
                booking=free_booking,
            ).exists(),
        )
        self.assertFalse(
            BonusTransaction.objects.filter(
                booking=free_booking,
            ).exists(),
        )
        self.assertEqual(
            Notification.objects.filter(
                booking=free_booking,
                kind=Notification.Kind.BOOKING_CONFIRMED,
                user=self.user,
            ).count(),
            1,
        )

    def test_batch_reports_invalid_records_and_confirms_valid_one(self):
        cancelled = self.create_booking(day_offset=0)
        past = self.create_booking(day_offset=1)
        valid = self.create_booking(day_offset=2)

        Booking.objects.filter(pk=cancelled.pk).update(
            status=Booking.Status.CANCELLED,
        )
        Booking.objects.filter(pk=past.pk).update(
            starts_at=timezone.now() - timedelta(hours=2),
            ends_at=timezone.now() - timedelta(hours=1),
        )

        response = self.run_action(
            "confirm_with_payment",
            cancelled,
            past,
            valid,
        )
        self.assertEqual(response.status_code, 200)

        for booking, expected_status in (
            (cancelled, Booking.Status.CANCELLED),
            (past, Booking.Status.PENDING),
        ):
            with self.subTest(booking=booking.pk):
                booking.refresh_from_db()
                self.assertEqual(
                    booking.status,
                    expected_status,
                )
                self.assertFalse(
                    Payment.objects.filter(
                        booking=booking,
                    ).exists(),
                )
                self.assertFalse(
                    Notification.objects.filter(
                        booking=booking,
                    ).exists(),
                )

        valid.refresh_from_db()
        self.assertEqual(
            valid.status,
            Booking.Status.CONFIRMED,
        )
        self.assertEqual(
            Payment.objects.filter(booking=valid).count(),
            1,
        )

    def test_staff_without_change_permission_cannot_run_action(self):
        booking = self.create_booking()

        staff = User.objects.create_user(
            username="view_only_staff",
            password="StaffTest!47River",
            is_staff=True,
        )
        permission = Permission.objects.get(
            content_type__app_label="bookings",
            codename="view_booking",
        )
        staff.user_permissions.add(permission)

        self.client.force_login(staff)

        response = self.run_action(
            "confirm_with_payment",
            booking,
        )
        self.assertIn(response.status_code, (200, 403))

        booking.refresh_from_db()
        self.assertEqual(
            booking.status,
            Booking.Status.PENDING,
        )
        self.assertFalse(
            Payment.objects.filter(booking=booking).exists(),
        )
        self.assertFalse(
            Notification.objects.filter(
                booking=booking,
            ).exists(),
        )

    def test_booking_form_ignores_forged_protected_fields(self):
        booking = self.create_booking()

        response = self.client.post(
            self.change_url(booking),
            {
                "membership": "",
                "status": Booking.Status.CONFIRMED,
                "total_price": "1.00",
                "user": self.other_user.pk,
                "_save": "Зберегти",
            },
        )
        self.assertEqual(response.status_code, 302)

        booking.refresh_from_db()
        self.assertEqual(
            booking.status,
            Booking.Status.PENDING,
        )
        self.assertEqual(
            booking.total_price,
            Decimal("400.00"),
        )
        self.assertEqual(booking.user_id, self.user.pk)
        self.assertFalse(
            Payment.objects.filter(booking=booking).exists(),
        )
        self.assertFalse(
            Notification.objects.filter(
                booking=booking,
            ).exists(),
        )

    def test_booking_form_rejects_foreign_membership(self):
        booking = self.create_booking()
        foreign_membership = MembershipService.purchase(
            user=self.other_user,
            plan_id=self.plan.pk,
            payment_successful=True,
        )

        response = self.client.post(
            self.change_url(booking),
            {
                "membership": foreign_membership.pk,
                "_save": "Зберегти",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["adminform"].form.errors,
        )

        booking.refresh_from_db()
        self.assertIsNone(booking.membership_id)
        self.assertEqual(
            booking.status,
            Booking.Status.PENDING,
        )

    def test_payment_records_cannot_be_added_changed_or_deleted(self):
        booking = self.create_booking()
        self.run_action("confirm_with_payment", booking)
        payment = Payment.objects.get(booking=booking)

        response = self.client.post(
            reverse(
                "admin:bookings_payment_change",
                args=[payment.pk],
            ),
            {
                "amount": "1.00",
                "status": Payment.Status.FAILED,
                "_save": "Зберегти",
            },
        )
        self.assertEqual(response.status_code, 302)

        payment.refresh_from_db()
        self.assertEqual(
            payment.amount,
            Decimal("400.00"),
        )
        self.assertEqual(
            payment.status,
            Payment.Status.SUCCESS,
        )

        response = self.client.post(
            reverse("admin:bookings_payment_add"),
            {
                "booking": booking.pk,
                "amount": "400.00",
                "status": Payment.Status.SUCCESS,
            },
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse(
                "admin:bookings_payment_delete",
                args=[payment.pk],
            ),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            Payment.objects.filter(pk=payment.pk).exists(),
        )