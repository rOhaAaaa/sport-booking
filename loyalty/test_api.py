from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from bookings.models import Booking
from catalog.models import Hall, SportsCenter, SportType

from .models import (
    BonusTransaction,
    LoyaltyCard,
    Membership,
    MembershipPlan,
)
from .services import MembershipService


User = get_user_model()


class LoyaltyAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="loyalty_client",
            password="SportDemo!47River",
        )
        cls.other_user = User.objects.create_user(
            username="other_loyalty_client",
            password="SportDemo!47River",
        )

        cls.plan = MembershipPlan.objects.create(
            name="Single visit",
            kind=MembershipPlan.Kind.SINGLE,
            price=Decimal("150.00"),
            validity_days=7,
            visit_limit=1,
            service_scope=MembershipPlan.ServiceScope.SESSIONS,
        )

        cls.own_membership = MembershipService.purchase(
            user=cls.user,
            plan_id=cls.plan.pk,
            payment_successful=True,
        )
        cls.other_membership = MembershipService.purchase(
            user=cls.other_user,
            plan_id=cls.plan.pk,
            payment_successful=True,
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

    def purchase(self, data):
        return self.client.post(
            reverse("loyalty:membership-purchase"),
            data,
            format="json",
            **self.csrf_headers(),
        )

    def list_items(self, response):
        self.assertEqual(response.status_code, 200)
        if isinstance(response.data, dict):
            return response.data["results"]
        return response.data

    def test_guest_can_read_plans(self):
        guest = APIClient(enforce_csrf_checks=True)

        response = guest.get(reverse("loyalty:plan-list"))
        items = self.list_items(response)
        self.assertEqual(
            {item["id"] for item in items},
            {self.plan.pk},
        )

        response = guest.get(
            reverse(
                "loyalty:plan-detail",
                args=[self.plan.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["price"], "150.00")

    def test_guest_cannot_access_private_resources(self):
        guest = APIClient(enforce_csrf_checks=True)

        urls = (
            reverse("loyalty:membership-list"),
            reverse(
                "loyalty:membership-detail",
                args=[self.own_membership.pk],
            ),
            reverse("loyalty:card"),
            reverse("loyalty:bonus-list"),
        )
        for url in urls:
            with self.subTest(url=url):
                response = guest.get(url)
                self.assertEqual(response.status_code, 403)

        count_before = Membership.objects.count()
        response = guest.post(
            reverse("loyalty:membership-purchase"),
            {
                "plan_id": self.plan.pk,
                "payment_successful": True,
            },
            format="json",
            **self.csrf_headers(guest),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            Membership.objects.count(),
            count_before,
        )

    def test_purchase_uses_current_user_and_plan_rules(self):
        count_before = Membership.objects.count()
        before = timezone.now()

        response = self.purchase({
            "plan_id": self.plan.pk,
            "payment_successful": True,
            "user": self.other_user.pk,
            "remaining_visits": 999,
            "status": "cancelled",
            "valid_until": "2099-01-01T00:00:00Z",
        })

        after = timezone.now()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Membership.objects.count(),
            count_before + 1,
        )

        membership = Membership.objects.get(
            pk=response.data["id"]
        )
        self.assertEqual(membership.user_id, self.user.pk)
        self.assertEqual(membership.plan_id, self.plan.pk)
        self.assertEqual(membership.remaining_visits, 1)
        self.assertEqual(
            membership.status,
            Membership.Status.ACTIVE,
        )
        self.assertGreaterEqual(
            membership.valid_from,
            before,
        )
        self.assertLessEqual(
            membership.valid_from,
            after,
        )
        self.assertEqual(
            membership.valid_until - membership.valid_from,
            timedelta(days=7),
        )
        self.assertEqual(
            response.data["plan"]["id"],
            self.plan.pk,
        )

    def test_failed_purchase_creates_no_membership(self):
        count_before = Membership.objects.count()

        response = self.purchase({
            "plan_id": self.plan.pk,
            "payment_successful": False,
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("non_field_errors", response.data)
        self.assertEqual(
            Membership.objects.count(),
            count_before,
        )

    def test_purchase_rejects_invalid_input(self):
        count_before = Membership.objects.count()
        cases = (
            {},
            {"plan_id": self.plan.pk},
            {"payment_successful": True},
            {
                "plan_id": 0,
                "payment_successful": True,
            },
            {
                "plan_id": 999999,
                "payment_successful": True,
            },
            {
                "plan_id": self.plan.pk,
                "payment_successful": "invalid",
            },
        )

        for data in cases:
            with self.subTest(data=data):
                response = self.purchase(data)
                self.assertEqual(response.status_code, 400)

        self.assertEqual(
            Membership.objects.count(),
            count_before,
        )

    def test_purchase_requires_csrf(self):
        count_before = Membership.objects.count()

        response = self.client.post(
            reverse("loyalty:membership-purchase"),
            {
                "plan_id": self.plan.pk,
                "payment_successful": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            Membership.objects.count(),
            count_before,
        )

    def test_memberships_are_visible_only_to_owner(self):
        response = self.client.get(
            reverse("loyalty:membership-list")
        )
        items = self.list_items(response)
        self.assertEqual(
            {item["id"] for item in items},
            {self.own_membership.pk},
        )

        response = self.client.get(
            reverse(
                "loyalty:membership-detail",
                args=[self.own_membership.pk],
            )
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            reverse(
                "loyalty:membership-detail",
                args=[self.other_membership.pk],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_card_is_created_once_with_zero_points(self):
        self.assertFalse(
            LoyaltyCard.objects.filter(
                user=self.user
            ).exists()
        )

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                response = self.client.get(
                    reverse("loyalty:card")
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.data["category"],
                    "standard",
                )
                self.assertEqual(
                    response.data["total_points"],
                    0,
                )

        self.assertEqual(
            LoyaltyCard.objects.filter(
                user=self.user
            ).count(),
            1,
        )

    def test_existing_card_category_is_preserved(self):
        card = LoyaltyCard.objects.create(
            user=self.user,
            category=LoyaltyCard.Category.PREMIUM,
        )

        response = self.client.get(reverse("loyalty:card"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], card.pk)
        self.assertEqual(
            response.data["category"],
            "premium",
        )
        card.refresh_from_db()
        self.assertEqual(
            card.category,
            LoyaltyCard.Category.PREMIUM,
        )

    def test_bonus_history_and_total_are_private(self):
        center = SportsCenter.objects.create(
            name="Bonus test center",
            address="Test address",
        )
        sport = SportType.objects.create(name="Test sport")
        hall = Hall.objects.create(
            center=center,
            sport_type=sport,
            name="Bonus test hall",
            capacity=10,
            hourly_price=Decimal("400.00"),
        )
        starts_at = timezone.now() + timedelta(days=1)

        own_card = LoyaltyCard.objects.create(user=self.user)
        other_card = LoyaltyCard.objects.create(
            user=self.other_user
        )

        own_bonus_ids = set()
        for index, points in enumerate((4, 6)):
            start = starts_at + timedelta(days=index)
            booking = Booking.objects.create(
                user=self.user,
                hall=hall,
                starts_at=start,
                ends_at=start + timedelta(hours=1),
                total_price=Decimal("400.00"),
                status=Booking.Status.CONFIRMED,
            )
            bonus = BonusTransaction.objects.create(
                card=own_card,
                booking=booking,
                points=points,
            )
            own_bonus_ids.add(bonus.pk)

        other_booking = Booking.objects.create(
            user=self.other_user,
            hall=hall,
            starts_at=starts_at + timedelta(days=3),
            ends_at=starts_at + timedelta(days=3, hours=1),
            total_price=Decimal("400.00"),
            status=Booking.Status.CONFIRMED,
        )
        other_bonus = BonusTransaction.objects.create(
            card=other_card,
            booking=other_booking,
            points=50,
        )

        response = self.client.get(
            reverse("loyalty:bonus-list")
        )
        items = self.list_items(response)
        self.assertEqual(
            {item["id"] for item in items},
            own_bonus_ids,
        )

        response = self.client.get(
            reverse(
                "loyalty:bonus-detail",
                args=[min(own_bonus_ids)],
            )
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            reverse(
                "loyalty:bonus-detail",
                args=[other_bonus.pk],
            )
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse("loyalty:card"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_points"], 10)

    def test_direct_resource_changes_are_not_allowed(self):
        card = LoyaltyCard.objects.create(user=self.user)
        headers = self.csrf_headers()

        cases = (
            (
                "post",
                reverse("loyalty:plan-list"),
                {"name": "Injected plan"},
            ),
            (
                "patch",
                reverse(
                    "loyalty:plan-detail",
                    args=[self.plan.pk],
                ),
                {"price": "0.00"},
            ),
            (
                "patch",
                reverse(
                    "loyalty:membership-detail",
                    args=[self.own_membership.pk],
                ),
                {"remaining_visits": 999},
            ),
            (
                "delete",
                reverse(
                    "loyalty:membership-detail",
                    args=[self.own_membership.pk],
                ),
                {},
            ),
            (
                "patch",
                reverse("loyalty:card"),
                {"category": "premium", "total_points": 999},
            ),
            (
                "post",
                reverse("loyalty:bonus-list"),
                {"points": 999},
            ),
        )

        for method, url, data in cases:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(
                    url,
                    data,
                    format="json",
                    **headers,
                )
                self.assertEqual(response.status_code, 405)

        self.plan.refresh_from_db()
        self.own_membership.refresh_from_db()
        card.refresh_from_db()
        self.assertEqual(
            self.plan.price,
            Decimal("150.00"),
        )
        self.assertEqual(
            self.own_membership.remaining_visits,
            1,
        )
        self.assertEqual(card.category, "standard")
        self.assertFalse(
            BonusTransaction.objects.exists()
        )

    def test_unlimited_corporate_purchase_preserves_card_category(self):
        card = LoyaltyCard.objects.create(
            user=self.user,
            category=LoyaltyCard.Category.STANDARD,
        )
        plan = MembershipPlan.objects.create(
            name="Unlimited corporate",
            kind=MembershipPlan.Kind.CORPORATE,
            price=Decimal("2500.00"),
            validity_days=30,
            visit_limit=None,
            service_scope=MembershipPlan.ServiceScope.BOTH,
        )

        response = self.purchase({
            "plan_id": plan.pk,
            "payment_successful": True,
        })

        self.assertEqual(response.status_code, 201)
        membership = Membership.objects.get(
            pk=response.data["id"]
        )
        self.assertIsNone(membership.remaining_visits)
        self.assertIsNone(response.data["remaining_visits"])
        self.assertEqual(
            membership.valid_until - membership.valid_from,
            timedelta(days=30),
        )
        card.refresh_from_db()
        self.assertEqual(
            card.category,
            LoyaltyCard.Category.STANDARD,
        )