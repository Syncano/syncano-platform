from django.urls import reverse
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase


class TestEndpointsAPI(SyncanoAPITestBase):
    def assert_url_works(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_endpoints_list_works(self):
        self.assert_url_works(reverse('v1.1:endpoints', args=(self.instance.name,)))
        self.assert_url_works(reverse('v2:endpoints', args=(self.instance.name,)))
