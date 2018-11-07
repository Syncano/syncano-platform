# coding=UTF8
from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.models import Instance


class TestSnippetsAPI(SyncanoAPITestBase):
    def assert_url_works(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_endpoints_list_works(self):
        self.assert_url_works(reverse('v1.1:snippets', args=(self.instance.name,)))
        self.assert_url_works(reverse('v2:snippets', args=(self.instance.name,)))


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestInstanceConfigAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1.1:instance-config', args=(self.instance.name,))

    def test_update(self):
        data = {'config': {'var1': 'var1', 'var2': 5}}

        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.config, data['config'])

        response = self.client.get(self.url)
        self.assertEqual(data, response.data)

    def test_partial_update(self):
        data = {'config': {'var1': 'var1'}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.config, data['config'])

        data = {'config': {'var1': 'var1', 'var2': 5}}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.config, data['config'])

        response = self.client.get(self.url)
        self.assertEqual(data, response.data)

    def test_invalid_access(self):
        other_instance = G(Instance)
        url = reverse('v1.1:instance-config', args=(other_instance.name,))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.put(url, {'config': {'key': 'value'}})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_shared_access(self):
        other_instance = G(Instance, name="sharedinstance")
        self.admin.add_to_instance(other_instance)
        url = reverse('v1.1:instance-config', args=(other_instance.name,))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {'key': 'value'}

        response = self.client.put(url, {'config': data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['config'], data)

        response = self.client.options(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anonymous_access_is_forbidden(self):
        del self.client.defaults['HTTP_X_API_KEY']
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.put(self.url, {'config': {'key': 'value'}})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
