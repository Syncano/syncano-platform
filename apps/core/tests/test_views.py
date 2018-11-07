from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.tests.mixins import CleanupTestCaseMixin


class TestViews(CleanupTestCaseMixin, APITestCase):
    def assert_url_works(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_links_endpoint_works(self):
        self.assert_url_works(reverse('v1:links'))
        self.assert_url_works(reverse('v1.1:links'))
        self.assert_url_works(reverse('v2:links'))
