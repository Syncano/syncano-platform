# coding=UTF8
import json

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.channels.models import Channel
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import DataObject, Klass
from apps.data.tests.test_filtering import TestAbstractFilterAPI
from apps.instances.helpers import set_current_instance
from apps.users.models import Group


class TestCoreFilteringAPI(TestAbstractFilterAPI):
    objects_number = 1

    def test_invalid_field_lookup(self):
        query = {'invalidfield': {'_gt': 1}}
        response = self.client.get(self.url, {'query': json.dumps(query)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_core_field_filtering(self):
        query = {'id': {'_eq': 2}}
        response = self.client.get(self.url, {'query': json.dumps(query)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_core_field_that_is_not_allowed(self):
        query = {'_klass': {'_eq': 2}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_lookup_name_fails(self):
        query = {'id': {'_equal': 2}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_json_fails(self):
        response = self.client.get(self.url, {'query': '{"}'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_json_without_dict_fails(self):
        query = [{'id': {'_eq': 2}}]
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_lookup_type_fails(self):
        query = {'id': [{'_eq': 2}]}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_too_many_values_in_inlookup_fail(self):
        query = {'id': {'_in': list(range(128))}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        query = {'id': {'_in': list(range(129))}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_value_in_inlookup_fails(self):
        query = {'id': {'_in': {'check': 1}}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        query = {'id': {'_in': [9223372036854775807]}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        query = {'updated_at': {'_in': [1]}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        query = {'updated_at': {'_in': [None]}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_value_in_existlookup_fails(self):
        query = {'id': {'_exists': 1}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_value_in_equallookup_fails(self):
        query = {'updated_at': {'_eq': 1}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        query = {'updated_at': {'_eq': None}}
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestRelatedObjectFilteringAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'string', 'type': 'string'},
                                      {'name': 'integer', 'type': 'integer'}],
                       name='test',
                       description='test')
        self.channel = G(Channel, name='channel')
        self.group = G(Group)
        self.object_data = {'1_string': 'test', '1_integer': 10}
        DataObject._meta.get_field('_data').reload_schema(None)
        self.object = G(DataObject, _klass=self.klass, _data=self.object_data.copy(),
                        channel=self.channel, group=self.group)
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def assert_filter(self, query, expected_count=1, expected_status=status.HTTP_200_OK):
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, expected_status)
        if expected_status == status.HTTP_200_OK:
            self.assertEqual(len(response.data['objects']), expected_count)

    def test_filtering_by_channel(self):
        self.assert_filter({'channel': {'_eq': self.channel.name}})
        self.assert_filter({'channel': {'_eq': 'zig'}}, expected_count=0)
        self.assert_filter({'channel': {'_in': ['zig', self.channel.name, 'zag']}})
        self.assert_filter({'channel': {'_in': ['zig', 'zag']}}, expected_count=0)

    def test_filtering_by_invalid_channel_value(self):
        self.assert_filter({'channel': {'_eq': 1}}, expected_status=status.HTTP_400_BAD_REQUEST)
        self.assert_filter({'channel': {'_in': ['zig', 1, 'zag']}}, expected_status=status.HTTP_400_BAD_REQUEST)

    def test_filtering_by_group(self):
        self.assert_filter({'group': {'_eq': self.group.id}})
        self.assert_filter({'group': {'_eq': 123}}, expected_count=0)
        self.assert_filter({'group': {'_in': [123, self.group.id, 321]}})
        self.assert_filter({'group': {'_in': [123, 321]}}, expected_count=0)

    def test_filtering_by_invalid_group_value(self):
        self.assert_filter({'group': {'_eq': 'zig'}}, expected_status=status.HTTP_400_BAD_REQUEST)
        self.assert_filter({'group': {'_in': ['zig', 1, 'zag']}}, expected_status=status.HTTP_400_BAD_REQUEST)


class TestDataObjectFilterByChannelRoomAPI(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.channel = G(Channel, name='testchannel', separate_rooms=True)

        self.klass = G(Klass, schema=[{'name': 'string', 'type': 'string'},
                                      {'name': 'integer', 'type': 'integer'}],
                       name='test',
                       description='test')

        G(DataObject, _klass=self.klass, channel=self.channel, channel_room='testroom')
        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_channel_room_lookups_eq_in(self):
        response = self.client.get(self.url, data={'query': json.dumps({'channel_room': {'_eq': 'testroom'}})})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

        response = self.client.get(self.url, data={'query': json.dumps({'channel_room': {'_in': ['testroom']}})})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_channel_room_lookups_fail_contains(self):
        response = self.client.get(self.url, data={'query': json.dumps({'channel_room': {'_contains': 'testroom'}})})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
