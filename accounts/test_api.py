from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from .models import UserProfile


User = get_user_model()


class AccountsAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "SportDemo!47River"
        cls.user = User.objects.create_user(
            username="existing_client",
            password=cls.password,
            email="existing@example.com",
        )
        UserProfile.objects.get_or_create(user=cls.user)
        cls.other_user = User.objects.create_user(
            username="other_client",
            password=cls.password,
        )
        UserProfile.objects.get_or_create(
            user=cls.other_user,
            defaults={"phone": "+380501111111"},
        )

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf_headers(self):
        response = self.client.get(reverse("accounts:csrf"))
        self.assertEqual(response.status_code, 200)
        return {
            "HTTP_X_CSRFTOKEN": response.data["csrfToken"],
        }

    def registration_data(self, **changes):
        data = {
            "username": "new_client",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "Client",
            "password": self.password,
            "password_confirm": self.password,
        }
        data.update(changes)
        return data

    def login_user(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.user.username,
                "password": self.password,
            },
            format="json",
            **self.csrf_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return {
            "HTTP_X_CSRFTOKEN": response.data["csrfToken"],
        }

    def test_guest_can_get_csrf_token(self):
        response = self.client.get(reverse("accounts:csrf"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["csrfToken"])

    def test_registration_creates_user_and_profile(self):
        response = self.client.post(
            reverse("accounts:register"),
            self.registration_data(
                is_staff=True,
                is_superuser=True,
            ),
            format="json",
            **self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="new_client")
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(
            UserProfile.objects.filter(user=user).exists()
        )
        self.assertNotIn("password", response.data)
        self.assertNotIn("password_confirm", response.data)

        profile_response = self.client.get(
            reverse("accounts:profile")
        )
        self.assertEqual(profile_response.status_code, 403)

    def test_registration_rejects_password_mismatch(self):
        response = self.client.post(
            reverse("accounts:register"),
            self.registration_data(
                password_confirm="AnotherPassword!82"
            ),
            format="json",
            **self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("password_confirm", response.data)
        self.assertFalse(
            User.objects.filter(username="new_client").exists()
        )

    def test_registration_rejects_weak_password(self):
        response = self.client.post(
            reverse("accounts:register"),
            self.registration_data(
                password="123",
                password_confirm="123",
            ),
            format="json",
            **self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        self.assertFalse(
            User.objects.filter(username="new_client").exists()
        )

    def test_registration_rejects_duplicate_username(self):
        response = self.client.post(
            reverse("accounts:register"),
            self.registration_data(
                username=self.user.username
            ),
            format="json",
            **self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)

    def test_registration_and_login_require_csrf(self):
        for route, data in (
            (
                "accounts:register",
                self.registration_data(),
            ),
            (
                "accounts:login",
                {
                    "username": self.user.username,
                    "password": self.password,
                },
            ),
        ):
            with self.subTest(route=route):
                response = self.client.post(
                    reverse(route),
                    data,
                    format="json",
                )
                self.assertEqual(response.status_code, 403)

        self.assertFalse(
            User.objects.filter(username="new_client").exists()
        )
        self.assertEqual(
            self.client.get(
                reverse("accounts:profile")
            ).status_code,
            403,
        )

    def test_login_opens_own_profile(self):
        self.login_user()

        response = self.client.get(
            reverse("accounts:profile")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["username"],
            self.user.username,
        )

    def test_wrong_password_does_not_open_session(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.user.username,
                "password": "WrongPassword!82",
            },
            format="json",
            **self.csrf_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.get(
                reverse("accounts:profile")
            ).status_code,
            403,
        )

    def test_guest_cannot_read_or_edit_profile(self):
        response = self.client.get(
            reverse("accounts:profile")
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.patch(
            reverse("accounts:profile"),
            {"phone": "+380672222222"},
            format="json",
            **self.csrf_headers(),
        )
        self.assertEqual(response.status_code, 403)

    def test_profile_update_changes_only_own_data(self):
        headers = self.login_user()

        response = self.client.patch(
            reverse("accounts:profile"),
            {
                "first_name": "Updated",
                "last_name": "Client",
                "email": "updated@example.com",
                "phone": "+380672222222",
                "preferences": "Yoga",
                "username": "changed_username",
                "user": self.other_user.pk,
                "is_staff": True,
                "is_superuser": True,
            },
            format="json",
            **headers,
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Client")
        self.assertEqual(
            self.user.email,
            "updated@example.com",
        )
        self.assertEqual(
            self.user.username,
            "existing_client",
        )
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.phone, "+380672222222")
        self.assertEqual(profile.preferences, "Yoga")

        other_profile = UserProfile.objects.get(
            user=self.other_user
        )
        self.assertEqual(
            other_profile.phone,
            "+380501111111",
        )
        self.other_user.refresh_from_db()
        self.assertEqual(self.other_user.first_name, "")

    def test_profile_update_and_logout_require_csrf(self):
        self.login_user()

        response = self.client.patch(
            reverse("accounts:profile"),
            {"phone": "+380679999999"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        profile = UserProfile.objects.get(user=self.user)
        self.assertNotEqual(
            profile.phone,
            "+380679999999",
        )

        response = self.client.post(
            reverse("accounts:logout"),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.client.get(
                reverse("accounts:profile")
            ).status_code,
            200,
        )

    def test_logout_closes_session(self):
        headers = self.login_user()

        response = self.client.post(
            reverse("accounts:logout"),
            {},
            format="json",
            **headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("accounts:profile")
            ).status_code,
            403,
        )