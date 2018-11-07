from django.urls import reverse
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase


class TestApiKeyDetailAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.apikey = self.instance.create_apikey()
        self.url = reverse('v2:apikey-detail', args=(self.instance.name, self.apikey.id,))

    def test_deprecated_parameters(self):
        data = {'description': 'something something',
                'ignore_acl': True,
                'allow_user_create': True,
                'allow_group_create': True,
                'allow_anonymous_read': True}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Other flags should be ignored in v2
        deprecated = {'allow_anonymous_read', 'allow_group_create', 'allow_user_create'}

        response = self.client.get(self.url)
        for k, v in data.items():
            if k in deprecated:
                self.assertNotIn(k, response.data)
            else:
                self.assertEqual(response.data[k], v)
