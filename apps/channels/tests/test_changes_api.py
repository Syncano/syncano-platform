from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.users.models import Group, Membership
from apps.users.tests.test_user_api import UserTestCase

from ..models import Channel


class TestChangesAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.channel = G(Channel, name='channel')
        self.url = reverse('v1:change-list', args=(self.instance.name, self.channel.name))

    def test_listing(self):
        self.channel.create_change()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertIsNotNone(response.data['objects'][0]['links']['self'])

    def test_last_id_filter(self):
        c1 = self.channel.create_change()
        c2 = self.channel.create_change()

        response = self.client.get(self.url, {'last_id': c1.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['id'], c2.id)
        self.assertIsNotNone(response.data['objects'][0]['links']['self'])

        c3 = self.channel.create_change()

        response = self.client.get(self.url, {'last_id': c1.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)
        self.assertEqual(response.data['objects'][0]['id'], c3.id)
        self.assertEqual(response.data['objects'][1]['id'], c2.id)


class TestChangesPermissions(UserTestCase):
    def create_channel(self, access_as='apikey', create_user=True, custom_publish=True, separate_rooms=True):
        super().init_data(access_as=access_as, create_user=create_user)
        self.group = G(Group)
        self.channel = G(Channel, name='channel', custom_publish=custom_publish,
                         type=Channel.TYPES.SEPARATE_ROOMS if separate_rooms else Channel.TYPES.DEFAULT,
                         group=self.group,
                         group_permissions=Channel.PERMISSIONS.PUBLISH)
        self.url = reverse('v1:change-list', args=(self.instance.name, self.channel.name))

    def test_listing_as_admin(self):
        self.create_channel(access_as='admin', create_user=False, separate_rooms=False)
        self.channel.create_change()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_listing_as_admin_with_room(self):
        self.create_channel(access_as='admin', create_user=False)
        self.channel.create_change(room='test')

        response = self.client.get(self.url, {'room': 'test2'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 0)

        response = self.client.get(self.url, {'room': 'test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_listing_as_user_with_room(self):
        self.create_channel()
        self.channel.create_change(room='test')

        response = self.client.get(self.url, {'room': 'test'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        G(Membership, user=self.user, group=self.group)
        response = self.client.get(self.url, {'room': 'test2'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 0)

        response = self.client.get(self.url, {'room': 'test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_listing_without_room_denied_for_users(self):
        self.create_channel()
        G(Membership, user=self.user, group=self.group)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get(self.url, {'room': 'test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
