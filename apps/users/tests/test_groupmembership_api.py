from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.users.models import Group, Membership, User
from apps.users.tests.test_user_api import UserTestCase


class TestGroupUserList(UserTestCase):
    def setUp(self):
        super().init_data('admin')
        self.group = G(Group, name='some_group')
        self.membership = G(Membership, user=self.user, group=self.group)
        self.url = reverse('v1:group-user-list', args=(self.instance.name, self.group.id))

    def test_listing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_listing_is_filtered_properly(self):
        another_user = G(User, username='test')
        another_group = G(Group, name='another_group')
        G(Membership, user=another_user, group=another_group)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['user']['id'], self.user.id)

    def test_adding_user_membership(self):
        another_user = G(User, username='test')

        response = self.client.post(self.url, {'user': another_user.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)

    def test_user_memberships_are_unique(self):
        response = self.client.post(self.url, {'user': self.user.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestGroupUserListKeyAccess(UserTestCase):
    def setUp(self):
        super().init_data()
        self.group = G(Group, name='some_group')
        self.membership = G(Membership, user=self.user, group=self.group)
        self.url = reverse('v1:group-user-list', args=(self.instance.name, self.group.id))

    def test_listing_returns_only_own_user(self):
        user = G(User, username='test2')
        G(Membership, user=user, group=self.group)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['user']['id'], self.user.id)


class TestGroupUserDetail(UserTestCase):
    def setUp(self):
        super().init_data('admin')
        self.group = G(Group, name='some_group')
        self.membership = G(Membership, user=self.user, group=self.group)
        self.url = reverse('v1:group-user-detail', args=(self.instance.name, self.group.id, self.user.id))

    def test_getting(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['user']['id'], self.user.id)

    def test_deleting_user_membership(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Membership.objects.exists())
        self.assertTrue(User.objects.exists())
