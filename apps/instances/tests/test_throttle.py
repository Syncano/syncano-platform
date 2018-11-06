from unittest import mock

from django.urls import reverse
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase


class TestThrottling(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:klass-list', args=(self.instance.name,))

    @mock.patch('apps.instances.throttling.InstanceRateThrottle.rate', '1/day')
    @mock.patch('apps.instances.throttling.InstanceRateThrottle.get_instance_rate', mock.MagicMock(return_value=1))
    def test_throttling(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
