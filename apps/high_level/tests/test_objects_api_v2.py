from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import DataObject, Klass
from apps.high_level.models import DataObjectHighLevelApi
from apps.instances.helpers import set_current_instance
from apps.users.models import User


class TestObjectsHighLevelAPI(SyncanoAPITestBase):
    disable_user_profile = False

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        schema = [
            {'name': 'name', 'type': 'string'},
            {'name': 'ref', 'type': 'reference', 'target': 'self'},
            {'name': 'user', 'type': 'reference', 'target': 'user'},
        ]
        self.klass = G(Klass, schema=schema, name='test', description='test')

        DataObject.load_klass(self.klass)
        self.object = G(DataObject, _klass=self.klass, name='a')

        self.user = G(User)
        DataObject.load_klass(self.klass)
        self.object_2 = G(DataObject, _klass=self.klass, name='b', user=self.user.pk, ref=self.object.pk)

        self.hla = G(DataObjectHighLevelApi, klass=self.klass)
        self.endpoint_url = reverse('v2:hla-objects-endpoint', args=[self.instance.name, self.hla.name])

    def test_run(self):
        response = self.client.get(self.endpoint_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('acl', response.data['objects'][0])

    def test_post(self):
        response = self.client.post(self.endpoint_url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('acl', response.data)
        self.assertEqual(DataObject.objects.filter(_klass=self.klass).count(), 3)

        response = self.client.get(self.endpoint_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 3)

    def test_post_with_apikey(self):
        self.klass.objects_acl = {}
        self.klass.save()

        apikey = self.instance.create_apikey()
        response = self.client.post(self.endpoint_url, HTTP_X_API_KEY=apikey.key)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        apikey = self.instance.create_apikey(ignore_acl=True)
        response = self.client.post(self.endpoint_url, HTTP_X_API_KEY=apikey.key)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_run_with_expand(self):
        self.hla.expand = 'ref'
        self.hla.save()

        response = self.client.get(self.endpoint_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(isinstance(response.data['objects'][1]['ref'], dict))
        self.assertTrue(response.data['objects'][1]['ref']['id'], self.object.pk)
        self.assertIn('acl', response.data['objects'][1]['ref'])
        self.assertEqual(response.data['objects'][0]['ref'], None)

    def test_run_with_expand_for_user(self):
        self.hla.expand = 'user'
        self.hla.save()

        response = self.client.get(self.endpoint_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(isinstance(response.data['objects'][1]['user'], dict))
        self.assertTrue(response.data['objects'][1]['user']['id'], self.user.pk)
        self.assertIn('acl', response.data['objects'][1]['user'])
        self.assertEqual(response.data['objects'][0]['user'], None)
