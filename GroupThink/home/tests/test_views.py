"""Tests for view functions."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class SimpleViewTest(TestCase):
    """Basic tests for view accessibility."""

    def setUp(self):
        """Create and log in a user for login_required views."""
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.force_login(self.user)

    def test_homepage_loads(self):
        """Ensure anonymous access to homepage."""
        self.client.logout()
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)

    def test_createpage_loads(self):
        """Test that create meeting page loads for authenticated users."""
        response = self.client.get(reverse("create_meeting"))
        self.assertEqual(response.status_code, 200)
