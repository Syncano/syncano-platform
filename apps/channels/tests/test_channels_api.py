# coding=UTF8
import json
from unittest import mock

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.channels.v1.views import CHANNEL_PAYLOAD_LIMIT
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.users.models import Group, Membership, User
from apps.users.tests.test_user_api import UserTestCase

from ..models import Change, Channel


class TestChannelsListAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.url = reverse('v1:channel-list', args=(self.instance.name,))

    def test_creation(self):
        data = {'name': 'ChaNNel', 'custom_publish': True, 'type': 'separate_rooms'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data['links']['self'])
        self.assertTrue(Channel.objects.filter(name=data['name']).exists())
        data['name'] = data['name'].lower()

        for key, value in data.items():
            self.assertEqual(response.data[key], value)

    def test_listing(self):
        G(Channel, name='channel')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 3)


class TestChannelsDetailAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.channel = G(Channel, name='channel', custom_publish=True, type=Channel.TYPES.SEPARATE_ROOMS)
        self.url = reverse('v1:channel-detail', args=(self.instance.name, self.channel.name))

    def test_updating_with_patch(self):
        data = {'custom_publish': False}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key, value in data.items():
            self.assertEqual(response.data[key], value)

    def test_updating_with_put(self):
        data = {'custom_publish': False}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for key, value in data.items():
            self.assertEqual(response.data[key], value)

    def test_deletion(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Channel.objects.filter(name=self.channel.name).exists())

        # Assert that deleting of default channel fails
        for channel_name in (Channel.DEFAULT_NAME, Channel.EVENTLOG_NAME):
            url = reverse('v1:channel-detail', args=(self.instance.name, channel_name))
            response = self.client.delete(url)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestChannelListingAsUser(UserTestCase):
    def setUp(self):
        super().init_data()
        self.url = reverse('v1:channel-list', args=(self.instance.name,))

    def test_listing_filtered_by_permissions(self):
        group = G(Group)
        G(Channel,
          name='channel1',
          group=group,
          group_permissions=Channel.PERMISSIONS.PUBLISH)
        G(Channel,
          name='channel2',
          group=group,
          group_permissions=Channel.PERMISSIONS.SUBSCRIBE)
        G(Channel,
          name='channel3',
          group=group,
          other_permissions=Channel.PERMISSIONS.SUBSCRIBE)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

        G(Membership, user=self.user, group=group)
        G(Membership, user=G(User), group=group)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 3)

    def test_listing_with_anonymous_read(self):
        del self.client.defaults['HTTP_X_USER_KEY']
        self.apikey.allow_anonymous_read = True
        self.apikey.save()
        group = G(Group)
        G(Channel,
          name='channel1',
          group=group,
          group_permissions=Channel.PERMISSIONS.SUBSCRIBE)
        G(Channel,
          name='channel3',
          group=group,
          other_permissions=Channel.PERMISSIONS.SUBSCRIBE)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)


class TestChannelPublish(UserTestCase):
    def create_channel(self, access_as='apikey', create_user=True, custom_publish=True, separate_rooms=True):
        super().init_data(access_as=access_as, create_user=create_user)
        self.group = G(Group)
        self.channel = G(Channel, name='channel', custom_publish=custom_publish,
                         type=Channel.TYPES.SEPARATE_ROOMS if separate_rooms else Channel.TYPES.DEFAULT,
                         group=self.group,
                         group_permissions=Channel.PERMISSIONS.PUBLISH)
        self.url = reverse('v1:channel-publish', args=(self.instance.name, self.channel.name))

    def test_publish_as_admin(self):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        data = {'payload': json.dumps({'key': 'value'})}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Change.list(channel=self.channel))

    def test_publish_as_json(self):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        data = {'payload': {'key': 'value'}}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Change.list(channel=self.channel))

    def test_incorrect_publish(self):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        data = {'payload': 'abc'}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Change.list(channel=self.channel))

    def test_passing_too_big_payload(self):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        data = {'payload': {'key_%d' % i: 'a' * int(CHANNEL_PAYLOAD_LIMIT / 10) for i in range(10)}}

        response = self.client.post(self.url, data)
        self.assertEquals(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    def test_publish_as_admin_with_room(self):
        self.create_channel(access_as='admin', create_user=False)
        data = {'payload': json.dumps({'key': 'wartość'}), 'room': 'ąę'}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Change.list(channel=self.channel, room='ąę'))

    def test_publish_as_user_with_room(self):
        self.create_channel()
        data = {'payload': json.dumps({'key': 'value'}), 'room': 'test'}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        G(Membership, user=self.user, group=self.group)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Change.list(channel=self.channel, room='test'))

    def test_publish_denied_without_custom_publish(self):
        self.create_channel(access_as='admin', create_user=False, custom_publish=False, separate_rooms=False)
        data = {'payload': json.dumps({'key': 'value'})}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_publish_denied_without_room(self):
        self.create_channel(access_as='admin', create_user=False)
        data = {'payload': json.dumps({'key': 'value'})}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_actually_calls_redis(self):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        data = {'payload': json.dumps({'key': 'value'})}

        self.client.post(self.url, data)
        change_list = Change.list(channel=self.channel)
        self.assertEqual(len(change_list), 1)


class TestChannelPoll(UserTestCase):
    def create_channel(self, access_as='apikey', create_user=True, custom_publish=True, separate_rooms=True):
        super().init_data(access_as=access_as, create_user=create_user)
        self.group = G(Group)
        self.channel = G(Channel, name='channel', custom_publish=custom_publish,
                         type=Channel.TYPES.SEPARATE_ROOMS if separate_rooms else Channel.TYPES.DEFAULT,
                         group=self.group,
                         group_permissions=Channel.PERMISSIONS.SUBSCRIBE)
        self.url = reverse('v1:channel-poll', args=(self.instance.name, self.channel.name))

    def test_poll_as_admin(self):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        change = self.channel.create_change()

        response = self.client.get(self.url, {'last_id': 0})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], change.id)

    def test_poll_as_admin_with_room(self):
        self.create_channel(access_as='admin', create_user=False)
        self.channel.create_change(room='room')
        change = self.channel.create_change(room='ąę')
        data = {'room': 'ąę', 'last_id': 0}

        response = self.client.get(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], change.id)

    def test_poll_as_user_with_room(self):
        self.create_channel()
        self.channel.create_change(room='room')
        old_change = self.channel.create_change(room='test')
        change = self.channel.create_change(room='test')
        data = {'room': 'test', 'last_id': old_change.id}

        response = self.client.get(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        G(Membership, user=self.user, group=self.group)
        response = self.client.get(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], change.id)

    def test_poll_denied_without_room(self):
        self.create_channel(access_as='admin', create_user=False)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_poll_with_last_id(self):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        change1 = self.channel.create_change()
        change2 = self.channel.create_change()

        response = self.client.get(self.url, {'last_id': change1.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Expect raw response from cache
        self.assertEqual(response.data['id'], change2.id)

    @mock.patch('apps.channels.v1.views.uwsgi')
    def test_poll_falls_back_to_uwsgi_handler(self, uwsgi_mock):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=True)

        response = self.client.get(self.url, {'room': 'abc'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)

    @mock.patch('apps.channels.v1.views.uwsgi')
    def test_poll_with_websocket_transport(self, uwsgi_mock):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=True)

        response = self.client.get(self.url, {'room': 'abc', 'transport': 'websocket'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uwsgi_mock.add_var.assert_any_call('OFFLOAD_HANDLER', 'apps.channels.handlers.ChannelWSHandler')

    @mock.patch('apps.channels.v1.views.uwsgi')
    def test_poll_with_last_id_falls_back_to_uwsgi_handler(self, uwsgi_mock):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        change = self.channel.create_change()

        response = self.client.get(self.url, {'last_id': change.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(uwsgi_mock.add_var.called)

    @mock.patch('apps.channels.v1.views.uwsgi')
    def test_uwsgi_valueerror_is_handled(self, uwsgi_mock):
        uwsgi_mock.add_var.side_effect = ValueError
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
