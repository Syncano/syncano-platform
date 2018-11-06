import json
from unittest import mock

from django.test import TestCase
from django_dynamic_fixture import G

from apps.channels.models import Channel
from apps.channels.v1.serializers import ChangeSerializer
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance

from ..tasks import GetChangeTask


class TestGetChangeTask(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.instance = G(Instance, name='testinstance')
        set_current_instance(self.instance)
        self.channel = G(Channel)

        self.channel.create_change()
        self.change = self.channel.create_change()
        self.change_serialized = json.dumps(ChangeSerializer(self.change, excluded_fields=('links', 'room',)).data)
        self.result_key = 'abc'

    @mock.patch('apps.channels.tasks.redis')
    def test_getting_change_with_last_id(self, redis_mock):
        GetChangeTask.delay(result_key=self.result_key, instance_pk=self.instance.pk, channel_pk=self.channel.pk,
                            last_id=self.change.id - 1)
        redis_mock.publish.assert_has_calls([mock.call(self.result_key, self.change_serialized),
                                             mock.call(self.result_key, '')])

    @mock.patch('apps.channels.tasks.redis')
    def test_getting_change_with_current_last_id_and_limit(self, redis_mock):
        change2 = self.channel.create_change()
        change2_serialized = json.dumps(ChangeSerializer(change2, excluded_fields=('links', 'room',)).data)
        # change3 that should be skipped in results
        self.channel.create_change()

        GetChangeTask.delay(result_key=self.result_key, instance_pk=self.instance.pk, channel_pk=self.channel.pk,
                            last_id=self.change.id - 1, current_last_id=change2.id, limit=100)
        redis_mock.publish.assert_has_calls([mock.call(self.result_key, self.change_serialized),
                                             mock.call(self.result_key, change2_serialized),
                                             mock.call(self.result_key, '')])
        redis_mock.reset_mock()

        GetChangeTask.delay(result_key=self.result_key, instance_pk=self.instance.pk, channel_pk=self.channel.pk,
                            last_id=self.change.id - 1, current_last_id=change2.id, limit=1)
        redis_mock.publish.assert_has_calls([mock.call(self.result_key, self.change_serialized),
                                             mock.call(self.result_key, '')])

    @mock.patch('apps.channels.tasks.redis')
    def test_getting_change_with_room(self, redis_mock):
        change = self.channel.create_change(room='abc')
        change_serialized = json.dumps(ChangeSerializer(change, excluded_fields=('links', 'room',)).data)
        GetChangeTask.delay(result_key=self.result_key, instance_pk=self.instance.pk, channel_pk=self.channel.pk,
                            last_id=self.change.id - 1, channel_room='abc')
        redis_mock.publish.assert_has_calls([mock.call(self.result_key, change_serialized),
                                             mock.call(self.result_key, '')])
