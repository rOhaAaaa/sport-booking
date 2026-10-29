from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import (
    Hall,
    Section,
    SportsCenter,
    SportType,
    Trainer,
    TrainingSession,
)


class CatalogAPITests(APITestCase):
    def setUp(self):
        self.yoga = SportType.objects.create(name="Йога")
        self.swimming = SportType.objects.create(name="Плавання")

        self.center = SportsCenter.objects.create(
            name="Актив",
            address="Адреса 1",
        )
        self.other_center = SportsCenter.objects.create(
            name="Енергія",
            address="Адреса 2",
        )

        self.hall = Hall.objects.create(
            center=self.center,
            sport_type=self.yoga,
            name="Зал йоги",
            capacity=15,
            hourly_price=Decimal("400.00"),
        )
        self.pool = Hall.objects.create(
            center=self.other_center,
            sport_type=self.swimming,
            name="Басейн",
            capacity=12,
            hourly_price=Decimal("800.00"),
        )

        self.section = Section.objects.create(
            sport_type=self.yoga,
            name="Йога для початківців",
            skill_level="beginner",
            age_category="adults",
        )
        self.advanced_section = Section.objects.create(
            sport_type=self.yoga,
            name="Йога для підлітків",
            skill_level="advanced",
            age_category="teens",
        )
        self.swimming_section = Section.objects.create(
            sport_type=self.swimming,
            name="Плавання",
            skill_level="beginner",
            age_category="adults",
        )

        self.trainer = Trainer.objects.create(
            full_name="Тестовий тренер",
            specialization="Йога та плавання",
        )

        self.start = (
            timezone.now() + timedelta(days=7)
        ).replace(microsecond=0)

        self.session = self.create_session(
            self.section, self.hall, self.start
        )
        self.later_session = self.create_session(
            self.advanced_section,
            self.hall,
            self.start + timedelta(days=1),
        )
        self.swimming_session = self.create_session(
            self.swimming_section,
            self.pool,
            self.start + timedelta(days=2),
        )

    def create_session(self, section, hall, starts_at):
        return TrainingSession.objects.create(
            section=section,
            hall=hall,
            trainer=self.trainer,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            capacity=10,
            price=Decimal("150.00"),
        )

    def get_ids(self, route, params=None):
        response = self.client.get(
            reverse(route),
            data=params or {},
        )
        self.assertEqual(response.status_code, 200)
        data = response.data
        if isinstance(data, dict):
            data = data["results"]
        return {item["id"] for item in data}

    def test_guest_can_view_all_catalog_resources(self):
        resources = (
            ("center", self.center),
            ("sport-type", self.yoga),
            ("hall", self.hall),
            ("section", self.section),
            ("trainer", self.trainer),
            ("session", self.session),
        )

        for name, obj in resources:
            with self.subTest(resource=name):
                self.assertIn(
                    obj.pk,
                    self.get_ids(f"{name}-list"),
                )
                response = self.client.get(
                    reverse(
                        f"{name}-detail",
                        args=[obj.pk],
                    )
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["id"], obj.pk)

    def test_halls_filter_by_sport_and_center(self):
        self.assertEqual(
            self.get_ids(
                "hall-list",
                {"sport_type": self.yoga.pk},
            ),
            {self.hall.pk},
        )
        self.assertEqual(
            self.get_ids(
                "hall-list",
                {"center": self.other_center.pk},
            ),
            {self.pool.pk},
        )

    def test_sections_filter_by_combined_parameters(self):
        self.assertEqual(
            self.get_ids(
                "section-list",
                {
                    "sport_type": self.yoga.pk,
                    "skill_level": "beginner",
                    "age_category": "adults",
                },
            ),
            {self.section.pk},
        )

    def test_sessions_filter_by_sport(self):
        self.assertEqual(
            self.get_ids(
                "session-list",
                {"sport_type": self.yoga.pk},
            ),
            {self.session.pk, self.later_session.pk},
        )

    def test_sessions_filter_by_section_properties(self):
        self.assertEqual(
            self.get_ids(
                "session-list",
                {
                    "sport_type": self.yoga.pk,
                    "skill_level": "advanced",
                    "age_category": "teens",
                },
            ),
            {self.later_session.pk},
        )

    def test_sessions_filter_by_time_window(self):
        self.assertEqual(
            self.get_ids(
                "session-list",
                {
                    "starts_after": (
                        self.start - timedelta(minutes=1)
                    ).isoformat(),
                    "starts_before": (
                        self.start + timedelta(hours=2)
                    ).isoformat(),
                },
            ),
            {self.session.pk},
        )

    def test_valid_filters_can_return_empty_list(self):
        self.assertEqual(
            self.get_ids(
                "hall-list",
                {
                    "sport_type": self.yoga.pk,
                    "center": self.other_center.pk,
                },
            ),
            set(),
        )

    def test_invalid_filter_values_return_400(self):
        cases = (
            ("hall-list", {"sport_type": "abc"}),
            ("section-list", {"skill_level": "unknown"}),
            ("section-list", {"age_category": "unknown"}),
            ("session-list", {"sport_type": "abc"}),
            ("session-list", {"starts_after": "wrong-date"}),
        )

        for route, params in cases:
            with self.subTest(route=route, params=params):
                response = self.client.get(
                    reverse(route),
                    data=params,
                )
                self.assertEqual(response.status_code, 400)

    def test_missing_resource_returns_404(self):
        response = self.client.get(
            reverse("hall-detail", args=[999999])
        )
        self.assertEqual(response.status_code, 404)

    def test_catalog_writes_are_not_allowed(self):
        admin = get_user_model().objects.create_user(
            username="catalog_admin",
            is_staff=True,
            is_superuser=True,
        )
        resources = (
            ("center", self.center),
            ("sport-type", self.yoga),
            ("hall", self.hall),
            ("section", self.section),
            ("trainer", self.trainer),
            ("session", self.session),
        )

        for user in (None, admin):
            self.client.force_authenticate(user=user)

            for name, obj in resources:
                with self.subTest(
                    user="admin" if user else "guest",
                    resource=name,
                ):
                    response = self.client.post(
                        reverse(f"{name}-list"),
                        data={},
                        format="json",
                    )
                    self.assertEqual(response.status_code, 405)

                    detail_url = reverse(
                        f"{name}-detail",
                        args=[obj.pk],
                    )
                    for method in ("put", "patch", "delete"):
                        response = getattr(self.client, method)(
                            detail_url,
                            data={},
                            format="json",
                        )
                        self.assertEqual(
                            response.status_code, 405
                        )

        self.assertTrue(
            Hall.objects.filter(pk=self.hall.pk).exists()
        )