from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from loyalty.models import LoyaltyCard

from .models import Notification, Offer


User = get_user_model()


class NotificationAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="notification_user",
            password="TestPass!47River",
        )
        self.other_user = User.objects.create_user(
            username="other_notification_user",
            password="TestPass!47River",
        )
        self.client = APIClient()
        self.client.force_login(self.user)

        self.now = timezone.now()

        self.offer = self.create_offer(
            "Загальна пропозиція",
            Offer.TargetCategory.ALL,
        )
        self.standard_offer = self.create_offer(
            "Стандартна пропозиція",
            Offer.TargetCategory.STANDARD,
        )
        self.premium_offer = self.create_offer(
            "Преміум пропозиція",
            Offer.TargetCategory.PREMIUM,
        )
        self.corporate_offer = self.create_offer(
            "Корпоративна пропозиція",
            Offer.TargetCategory.CORPORATE,
        )

        self.unread = Notification.objects.create(
            user=self.user,
            kind=Notification.Kind.INFO,
            message="Непрочитане повідомлення",
        )
        self.read = Notification.objects.create(
            user=self.user,
            kind=Notification.Kind.INFO,
            message="Прочитане повідомлення",
            is_read=True,
        )
        self.offer_notification = Notification.objects.create(
            user=self.user,
            kind=Notification.Kind.OFFER,
            message="Нова пропозиція",
            offer=self.offer,
        )
        self.foreign = Notification.objects.create(
            user=self.other_user,
            kind=Notification.Kind.INFO,
            message="Чуже повідомлення",
        )

        self.messages_url = "/api/notifications/messages/"
        self.count_url = (
            "/api/notifications/messages/unread-count/"
        )
        self.offers_url = "/api/notifications/offers/"

    def create_offer(self, title, category, **overrides):
        data = {
            "title": title,
            "description": "Опис тестової пропозиції",
            "starts_at": self.now - timedelta(days=1),
            "ends_at": self.now + timedelta(days=1),
            "target_card_category": category,
        }
        data.update(overrides)
        return Offer.objects.create(**data)

    def message_url(self, notification):
        return f"{self.messages_url}{notification.pk}/"

    def read_url(self, notification):
        return f"{self.message_url(notification)}read/"

    def offer_url(self, offer):
        return f"{self.offers_url}{offer.pk}/"

    def test_guest_cannot_access_private_endpoints(self):
        guest = APIClient()

        urls = [
            self.messages_url,
            self.message_url(self.unread),
            self.count_url,
            self.offers_url,
            self.offer_url(self.offer),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = guest.get(url)
                self.assertEqual(response.status_code, 403)

        response = guest.post(
            self.read_url(self.unread),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_messages_include_only_current_users_records(self):
        response = self.client.get(self.messages_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["id"] for item in response.data},
            {
                self.unread.pk,
                self.read.pk,
                self.offer_notification.pk,
            },
        )

        response = self.client.get(
            self.message_url(self.unread),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["message"],
            self.unread.message,
        )

        response = self.client.get(
            self.message_url(self.foreign),
        )
        self.assertEqual(response.status_code, 404)

    def test_filters_work_separately_and_together(self):
        cases = [
            (
                {"is_read": "false"},
                {self.unread.pk, self.offer_notification.pk},
            ),
            (
                {"is_read": "true"},
                {self.read.pk},
            ),
            (
                {"kind": Notification.Kind.OFFER},
                {self.offer_notification.pk},
            ),
            (
                {
                    "kind": Notification.Kind.INFO,
                    "is_read": "false",
                },
                {self.unread.pk},
            ),
        ]

        for params, expected_ids in cases:
            with self.subTest(params=params):
                response = self.client.get(
                    self.messages_url,
                    params,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {item["id"] for item in response.data},
                    expected_ids,
                )

    def test_invalid_filters_return_400(self):
        for params in (
            {"is_read": "not-a-boolean"},
            {"kind": "unknown"},
        ):
            with self.subTest(params=params):
                response = self.client.get(
                    self.messages_url,
                    params,
                )
                self.assertEqual(response.status_code, 400)

    def test_unread_count_excludes_read_and_foreign_messages(self):
        response = self.client.get(self.count_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unread_count"], 2)

    def test_mark_read_is_idempotent_and_preserves_content(self):
        original_count = Notification.objects.count()
        original_message = self.unread.message

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                response = self.client.post(
                    self.read_url(self.unread),
                    {},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data["is_read"])

                self.unread.refresh_from_db()
                self.assertTrue(self.unread.is_read)
                self.assertEqual(
                    self.unread.message,
                    original_message,
                )

                count_response = self.client.get(
                    self.count_url,
                )
                self.assertEqual(
                    count_response.data["unread_count"],
                    1,
                )

        self.assertEqual(
            Notification.objects.count(),
            original_count,
        )

    def test_cannot_mark_foreign_message_as_read(self):
        response = self.client.post(
            self.read_url(self.foreign),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertFalse(self.foreign.is_read)

    def test_mark_read_requires_csrf_for_session_authentication(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(
            self.read_url(self.unread),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.unread.refresh_from_db()
        self.assertFalse(self.unread.is_read)

    def test_direct_writes_are_not_allowed(self):
        requests = [
            ("post", self.messages_url),
            ("patch", self.message_url(self.unread)),
            ("delete", self.message_url(self.unread)),
            ("post", self.offers_url),
            ("patch", self.offer_url(self.offer)),
            ("delete", self.offer_url(self.offer)),
        ]

        for method, url in requests:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(
                    url,
                    {},
                    format="json",
                )
                self.assertEqual(response.status_code, 405)

        self.unread.refresh_from_db()
        self.assertFalse(self.unread.is_read)
        self.assertTrue(
            Offer.objects.filter(pk=self.offer.pk).exists(),
        )

    def test_user_without_card_gets_standard_offers_without_card_creation(self):
        LoyaltyCard.objects.filter(user=self.user).delete()

        response = self.client.get(self.offers_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["id"] for item in response.data},
            {self.offer.pk, self.standard_offer.pk},
        )
        self.assertFalse(
            LoyaltyCard.objects.filter(user=self.user).exists(),
        )

    def test_offers_match_each_card_category(self):
        cases = [
            (
                LoyaltyCard.Category.STANDARD,
                self.standard_offer,
            ),
            (
                LoyaltyCard.Category.PREMIUM,
                self.premium_offer,
            ),
            (
                LoyaltyCard.Category.CORPORATE,
                self.corporate_offer,
            ),
        ]

        for category, targeted_offer in cases:
            with self.subTest(category=category):
                LoyaltyCard.objects.update_or_create(
                    user=self.user,
                    defaults={"category": category},
                )

                response = self.client.get(self.offers_url)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {item["id"] for item in response.data},
                    {self.offer.pk, targeted_offer.pk},
                )

    def test_offer_time_boundaries_and_detail_access(self):
        starting_now = self.create_offer(
            "Починається зараз",
            Offer.TargetCategory.ALL,
            starts_at=self.now,
        )
        ending_now = self.create_offer(
            "Завершується зараз",
            Offer.TargetCategory.ALL,
            ends_at=self.now,
        )
        future = self.create_offer(
            "Майбутня пропозиція",
            Offer.TargetCategory.ALL,
            starts_at=self.now + timedelta(hours=1),
        )

        LoyaltyCard.objects.update_or_create(
            user=self.user,
            defaults={
                "category": LoyaltyCard.Category.STANDARD,
            },
        )

        with patch(
            "notifications.services.timezone.now",
            return_value=self.now,
        ):
            response = self.client.get(self.offers_url)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                {item["id"] for item in response.data},
                {
                    self.offer.pk,
                    self.standard_offer.pk,
                    starting_now.pk,
                },
            )

            response = self.client.get(
                self.offer_url(starting_now),
            )
            self.assertEqual(response.status_code, 200)

            for unavailable in (
                ending_now,
                future,
                self.premium_offer,
                self.corporate_offer,
            ):
                with self.subTest(offer=unavailable.title):
                    response = self.client.get(
                        self.offer_url(unavailable),
                    )
                    self.assertEqual(
                        response.status_code,
                        404,
                    )