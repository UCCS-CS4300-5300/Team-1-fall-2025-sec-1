from django.test import TestCase
from django.urls import reverse

class SimpleViewTest(TestCase):
    def test_homepage_loads(self):
        response = self.client.get(reverse("index")) 
        self.assertEqual(response.status_code, 200)

    def test_createpage_loads(self):
        response = self.client.get(reverse("create_meeting"))
        self.assertEqual(response.status_code, 200)
