from django.urls import reverse
from rest_framework import status

from apps.apikeys.models import ApiKey
from apps.core.helpers import make_token
from apps.core.tests.testcases import SyncanoAPITestBase


class TestApiKeyListAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:apikey-list', args=(self.instance.name,))

    def test_listing_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_listing_api_keys_for_instance(self):
        apikey = self.instance.create_apikey()
        response = self.client.get(self.url)
        self.assertContains(response, apikey.key)

    def test_post_without_description_is_successful(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_post_creates_api_key(self):
        response = self.client.post(self.url, {'ignore_acl': True})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(self.url)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['ignore_acl'], True)


class TestApiKeyListKeyAccessAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.apikey = self.instance.create_apikey()
        self.url = reverse('v1:apikey-list', args=(self.instance.name,))
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key

    def test_returns_only_own_apikey(self):
        self.instance.create_apikey()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['id'], self.apikey.id)

    def test_creating_new_key_is_denied(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestAccessByToken(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:apikey-list', args=(self.instance.name,))
        del self.client.defaults['HTTP_X_API_KEY']

    def test_auth_by_token(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.defaults['HTTP_X_API_KEY'] = make_token(self.instance)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_auth_by_expired_token(self):
        self.client.defaults['HTTP_X_API_KEY'] = make_token(self.instance, -10)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestApiKeyDetailAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.apikey = self.instance.create_apikey()
        self.url = reverse('v1:apikey-detail', args=(self.instance.name, self.apikey.id,))

    def test_getting_one_api_key(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['links']['self'])

    def test_delete_api_key(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ApiKey.objects.filter(pk=self.apikey.id).exists())

    def test_resetting_api_key(self):
        response = self.client.post(reverse('v1:apikey-reset-key', args=(self.instance.name, self.apikey.id,)))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['api_key'], self.apikey.key)

    def test_updating_api_key(self):
        data = {'description': 'something something',
                'ignore_acl': True,
                'allow_user_create': True,
                'allow_group_create': True,
                'allow_anonymous_read': True}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(self.url)
        for k, v in data.items():
            self.assertEqual(response.data[k], v)


class TestApiKeyDetailKeyAccessAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.apikey = self.instance.create_apikey()
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.url = reverse('v1:apikey-detail', args=(self.instance.name, self.apikey.id,))

    def test_getting_own_api_key(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_getting_other_api_key(self):
        new_apikey = self.instance.create_apikey()
        response = self.client.get(reverse('v1:apikey-detail', args=(self.instance.name, new_apikey.id,)))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_api_key_is_denied(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_resetting_api_key_is_denied(self):
        response = self.client.post(reverse('v1:apikey-reset-key', args=(self.instance.name, self.apikey.id,)))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_updating_api_key_is_denied(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
