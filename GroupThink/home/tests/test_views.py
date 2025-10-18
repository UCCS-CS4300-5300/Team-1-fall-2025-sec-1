from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User


class SimpleViewTest(TestCase):
    def setUp(self):
        # create and log in a user for login_required views
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client.force_login(self.user)

    def test_homepage_loads(self):
        # Ensure anonymous access to homepage (index redirects for authenticated users)
        self.client.logout()
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)

    def test_createpage_loads(self):
        response = self.client.get(reverse("create_meeting"))
        self.assertEqual(response.status_code, 200)
