from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import NotificationLog, PriceAlert, UserProfile
from .price_logic import should_trigger_alert

User = get_user_model()


class PriceThresholdTest(TestCase):
    def test_price_below_threshold_triggers_alert(self):
        self.assertTrue(should_trigger_alert(4200, 4500))

    def test_price_above_threshold_does_not_trigger(self):
        self.assertFalse(should_trigger_alert(5000, 4500))

    def test_price_equal_to_threshold_triggers_alert(self):
        self.assertTrue(should_trigger_alert(4500, 4500))


class NotificationLogTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")
        self.alert = PriceAlert.objects.create(
            user=self.user, origin="DEL", destination="BOM",
            threshold_price=4500, status=PriceAlert.Status.ACTIVE,
        )

    def test_notification_log_created_with_correct_message(self):
        log = NotificationLog.objects.create(
            alert=self.alert, triggered_price=Decimal("4200"),
            message="Price dropped to 4200 for DEL-BOM",
        )
        self.assertEqual(log.triggered_price, Decimal("4200"))
        self.assertEqual(log.alert, self.alert)
        self.assertIn("DEL-BOM", log.message)


class AlertScopingTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="user1", password="pass12345")
        self.user2 = User.objects.create_user(username="user2", password="pass12345")
        self.alert1 = PriceAlert.objects.create(
            user=self.user1, origin="DEL", destination="BOM", threshold_price=4500,
        )
        self.alert2 = PriceAlert.objects.create(
            user=self.user2, origin="BLR", destination="HYD", threshold_price=2000,
        )
        self.client = APIClient()

    def test_user_only_sees_own_alerts(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get("/api/alerts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["origin"], "DEL")

    def test_user_cannot_see_other_users_alerts(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get("/api/alerts/")
        self.assertNotIn(self.alert2.id, [item["id"] for item in response.data])


class AuthenticationAndPermissionsTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_registration_creates_user_profile_and_token(self):
        response = self.client.post("/api/auth/register/", {
            "username": "newuser", "password": "a-secure-password", "email": "new@example.com",
            "role": "admin",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="newuser")
        self.assertEqual(user.profile.role, UserProfile.Role.USER)
        self.assertIn("access", response.data)

    def test_duplicate_username_returns_400(self):
        User.objects.create_user(username="taken", password="password123")
        response = self.client.post("/api/auth/register/", {
            "username": "taken", "password": "password123",
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_regular_user_cannot_access_admin_summary(self):
        user = User.objects.create_user(username="ordinary", password="password123")
        self.client.force_authenticate(user=user)
        response = self.client.get("/api/admin/summary/")
        self.assertEqual(response.status_code, 403)
