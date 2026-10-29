from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import Membership, MembershipPlan
from .services import MembershipService


class MembershipPurchaseTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="buyer",
        )
        self.plan = MembershipPlan.objects.create(
            name="Місячний тариф",
            kind=MembershipPlan.Kind.MONTHLY,
            price=Decimal("1000.00"),
            validity_days=30,
            visit_limit=8,
            service_scope=MembershipPlan.ServiceScope.SESSIONS,
        )

    def test_purchase_sets_dates_balance_and_status(self):
        now = timezone.now()

        with patch("loyalty.services.timezone.now", return_value=now):
            membership = MembershipService.purchase(
                self.user,
                self.plan.pk,
                payment_successful=True,
            )

        self.assertEqual(membership.user_id, self.user.pk)
        self.assertEqual(membership.plan_id, self.plan.pk)
        self.assertEqual(membership.valid_from, now)
        self.assertEqual(
            membership.valid_until,
            now + timedelta(days=30),
        )
        self.assertEqual(membership.remaining_visits, 8)
        self.assertEqual(membership.status, Membership.Status.ACTIVE)
        self.assertEqual(Membership.objects.count(), 1)

    def test_unlimited_plan_has_empty_balance(self):
        self.plan.visit_limit = None
        self.plan.save(update_fields=["visit_limit"])

        membership = MembershipService.purchase(
            self.user,
            self.plan.pk,
            payment_successful=True,
        )

        self.assertIsNone(membership.remaining_visits)

    def test_single_plan_has_one_use(self):
        self.plan.kind = MembershipPlan.Kind.SINGLE
        self.plan.visit_limit = 1
        self.plan.validity_days = 7
        self.plan.save()

        membership = MembershipService.purchase(
            self.user,
            self.plan.pk,
            payment_successful=True,
        )

        self.assertEqual(membership.remaining_visits, 1)
        self.assertEqual(
            membership.valid_until - membership.valid_from,
            timedelta(days=7),
        )

    def test_failed_payment_does_not_create_membership(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Імітована оплата неуспішна",
        ):
            MembershipService.purchase(
                self.user,
                self.plan.pk,
                payment_successful=False,
            )

        self.assertEqual(Membership.objects.count(), 0)

    def test_missing_plan_is_rejected(self):
        missing_id = self.plan.pk
        self.plan.delete()

        with self.assertRaisesMessage(
            ValidationError,
            "Тариф абонемента не знайдено",
        ):
            MembershipService.purchase(
                self.user,
                missing_id,
                payment_successful=True,
            )

        self.assertEqual(Membership.objects.count(), 0)

    def test_anonymous_user_is_rejected(self):
        with self.assertRaisesMessage(
            ValidationError,
            "авторизованому користувачу",
        ):
            MembershipService.purchase(
                AnonymousUser(),
                self.plan.pk,
                payment_successful=True,
            )

        self.assertEqual(Membership.objects.count(), 0)

    def test_inactive_user_is_rejected(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        with self.assertRaisesMessage(
            ValidationError,
            "активному авторизованому користувачу",
        ):
            MembershipService.purchase(
                self.user,
                self.plan.pk,
                payment_successful=True,
            )

        self.assertEqual(Membership.objects.count(), 0)