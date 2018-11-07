from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.users.models import Group, Membership, User
from apps.users.tests.test_user_api import UserTestCase


class TestUserGroupList(UserTestCase):
    def setUp(self):
        super().init_data('admin')
        self.group = G(Group, label='some_group')
        self.membership = G(Membership, user=self.user, group=self.group)
        self.url = reverse('v1:user-group-list', args=(self.instance.name, self.user.id))

    def test_listing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_listing_is_filtered_properly(self):
        another_user = G(User, userlabel='test')
        another_group = G(Group, label='another_group')
        G(Membership, user=another_user, group=another_group)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['group']['id'], self.group.id)

    def test_adding_group_membership(self):
        another_group = G(Group, label='new_group')
        response = self.client.post(self.url, {'group': another_group.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)

    @override_settings(USER_GROUP_MAX_COUNT=2)
    def test_if_can_create_after_limit_reached(self):
        another_group = G(Group, label='new_group')
        response = self.client.post(self.url, {'group': another_group.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        another_group = G(Group, label='new_group2')
        response = self.client.post(self.url, {'group': another_group.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_group_memberships_are_unique(self):
        response = self.client.post(self.url, {'group': self.group.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestUserGroupListKeyAccess(UserTestCase):
    def setUp(self):
        super().init_data()
        self.group = G(Group, label='some_group')
        self.membership = G(Membership, user=self.user, group=self.group)
        self.url = reverse('v1:user-group-list', args=(self.instance.name, self.user.id))

    def test_listing(self):
        G(Group, label='some_group_2')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_listing_other_users_group_is_denied(self):
        user = G(User, userlabel='john23@doe.com')
        self.url = reverse('v1:user-group-list', args=(self.instance.name, user.id))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestUserGroupDetail(UserTestCase):
    def setUp(self):
        super().init_data('admin')
        self.group = G(Group, label='some_group')
        self.membership = G(Membership, user=self.user, group=self.group)
        self.url = reverse('v1:user-group-detail', args=(self.instance.name, self.user.id, self.group.id))

    def test_getting(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['group']['id'], self.group.id)

    def test_deleting_group_membership(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Membership.objects.exists())
        self.assertTrue(Group.objects.exists())
