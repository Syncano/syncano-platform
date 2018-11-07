from unittest import mock

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.channels.models import Channel
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance


class TestThrottling(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.channel = G(Channel, name='channel')
        self.url = reverse('v1:channel-poll', args=(self.instance.name, self.channel.name))

    @mock.patch('apps.channels.v1.views.uwsgi', mock.MagicMock())
    @mock.patch('apps.instances.throttling.InstanceRateThrottle.rate', '1/day')
    @mock.patch('apps.instances.throttling.InstanceRateThrottle.get_instance_rate', mock.MagicMock(return_value=1))
    def test_instances_throttling_is_not_affecting_polling(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @mock.patch('apps.channels.v1.views.uwsgi', mock.MagicMock())
    @mock.patch('apps.channels.throttling.ChannelPollRateThrottle.rate', '1/day')
    @mock.patch('apps.channels.throttling.ChannelPollRateThrottle.get_instance_rate',
                mock.MagicMock(return_value=1))
    def test_polling_throttling(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
