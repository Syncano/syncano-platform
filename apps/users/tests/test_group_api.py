from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.users.models import Group
from apps.users.tests.test_user_api import UserTestCase


class TestGroupList(UserTestCase):
    def setUp(self):
        super().init_data('admin', create_user=False)
        self.group = G(Group, label='some_group')

        self.url = reverse('v1:group-list', args=(self.instance.name,))

    def test_listing(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_adding_group(self):
        group_data = {'label': 'new_group'}
        response = self.client.post(self.url, group_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        group = Group.objects.last()
        self.assertEqual(group.label, (group_data['label']))

    def test_adding_group_with_name(self):
        group_data = {'label': 'new_group', 'name': 'abc'}
        response = self.client.post(self.url, group_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        group = Group.objects.last()
        self.assertDictContainsSubset(group_data, group.__dict__)


class TestGroupDetail(UserTestCase):
    def setUp(self):
        super().init_data('admin', create_user=False)
        self.group = G(Group, label='some_group')

        self.url = reverse('v1:group-detail', args=(self.instance.name, self.group.id,))

    def test_getting(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.group.id)

    def test_updating_group(self):
        group_data = {'label': 'new_name'}

        response = self.client.put(self.url, group_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        group = Group.objects.first()
        self.assertEqual(group.label, group_data['label'])

    def test_deleting_group(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Group.objects.exists())


class TestGroupListWithAllowGroupCreateApiKey(TestGroupList):
    def setUp(self):
        super().setUp()

        # overwrite an api key
        self.apikey = self.instance.create_apikey(allow_group_create=True).key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
