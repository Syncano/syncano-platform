import json

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.settings import api_settings

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import DataObject, Klass
from apps.high_level.models import DataObjectHighLevelApi
from apps.instances.helpers import set_current_instance
from apps.users.models import User


class TestObjectsHighLevelAPI(SyncanoAPITestBase):
    disable_user_profile = False

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        schema = [
            {'name': 'name', 'type': 'string', 'order_index': True, 'filter_index': True},
            {'name': 'field2', 'type': 'string', 'order_index': True, 'filter_index': True},
            {'name': 'field3', 'type': 'string', 'order_index': True, 'filter_index': True},
            {'name': 'ref', 'type': 'reference', 'target': 'self'},
            {'name': 'user', 'type': 'reference', 'target': 'user'},
        ]
        self.klass = G(Klass, schema=schema, name='test', description='test')

        DataObject.load_klass(self.klass)
        self.object = G(DataObject, _klass=self.klass, name='a', field2='b', field3='c')

        self.user = G(User)
        DataObject.load_klass(self.klass)
        self.object = G(DataObject, _klass=self.klass, name='b', field2='a', field3='d',
                        ref=self.object.pk, user=self.user.pk)

        self.hla = G(DataObjectHighLevelApi, klass=self.klass)
        self.get_url = reverse('v1:hla-objects-get', args=[self.instance.name, self.hla.name])
        self.list_url = reverse('v1:hla-objects-list', args=[self.instance.name])

    def test_list(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['objects'][0]['links']['self'])

    def test_create(self):
        data = {'class': self.klass.name, 'name': 'DuMMy'}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], data['name'].lower())

    def test_create_with_invalid_page_size(self):
        data = {'class': self.klass.name, 'name': 'DuMMy', 'page_size': 2 * api_settings.PAGE_SIZE}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data = {'class': self.klass.name, 'name': 'DuMMy', 'page_size': -10}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expand_and_exclude_fields_validation(self):
        data = {'class': self.klass.name, 'name': 'DuMMy', 'expand': 'field1, field2'}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data = {'class': self.klass.name, 'name': 'DuMMy', 'excluded_fields': 'field1, field2'}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data = {'class': self.klass.name, 'name': 'DuMMy', 'excluded_fields': '[field1, field2]'}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data = {'class': self.klass.name, 'name': 'DuMMy', 'excluded_fields': 'field1,field2'}
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_delete(self):
        url = reverse('v1:hla-objects-detail', args=[self.instance.name, self.hla.name])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_run(self):
        response = self.client.get(self.get_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('owner_permissions', response.data['objects'][0])

    def test_rename(self):
        new_name = 'new-name'
        url = reverse('v1:hla-objects-rename', args=[self.instance.name, self.hla.name])
        response = self.client.post(url, {'new_name': new_name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], new_name)

        url = reverse('v1:hla-objects-detail', args=[self.instance.name, new_name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_rename_is_validated(self):
        G(DataObjectHighLevelApi, name='new-name')
        url = reverse('v1:hla-objects-rename', args=[self.instance.name, self.hla.name])
        # Test already existing name
        response = self.client.post(url, {'new_name': 'new-name'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_run_with_query(self):
        self.hla.query = {'name': {'_eq': 'a'}}
        self.hla.save()

        response = self.client.get(self.get_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['name'], 'a')

        query = {'field3': {'_eq': 'c'}}
        response = self.client.get(self.get_url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['field3'], 'c')

    def test_run_with_fields(self):
        self.hla.fields = 'field2,field3'
        self.hla.save()

        response = self.client.get(self.get_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for obj in response.data['objects']:
            keys = list(obj.keys())
            self.assertEqual(len(keys), 2)
            self.assertEqual(keys, ['field2', 'field3'])

        response = self.client.get(self.get_url, {'fields': 'field3'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for obj in response.data['objects']:
            keys = list(obj.keys())
            self.assertEqual(len(keys), 1)
            self.assertEqual(keys, ['field3'])

    def test_run_with_excluded_fields(self):
        self.hla.excluded_fields = 'field2'
        self.hla.save()

        response = self.client.get(self.get_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for obj in response.data['objects']:
            self.assertFalse('field2' in obj.keys())

        response = self.client.get(self.get_url, {'excluded_fields': 'field3'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for obj in response.data['objects']:
            self.assertFalse('field3' in obj.keys())

    def test_run_with_order_by(self):
        self.hla.order_by = 'field2'
        self.hla.save()

        response = self.client.get(self.get_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        objects = [o['field2'] for o in response.data['objects']]
        self.assertEqual(objects, ['a', 'b'])

        response = self.client.get(self.get_url, {'order_by': 'field3'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        objects = [o['field2'] for o in response.data['objects']]
        self.assertEqual(objects, ['b', 'a'])

    def test_run_with_page_size(self):
        self.hla.page_size = 1
        self.hla.save()

        response = self.client.get(self.get_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

        response = self.client.get(self.get_url, {'page_size': 2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)

    def test_run_with_expand(self):
        self.hla.expand = 'ref'
        self.hla.save()

        response = self.client.get(self.get_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(isinstance(response.data['objects'][1]['ref'], dict))
        self.assertTrue(response.data['objects'][1]['ref']['id'], self.object.pk)
        self.assertIn('owner', response.data['objects'][1]['ref'])
        self.assertEqual(response.data['objects'][0]['ref'], None)

    def test_run_with_expand_for_user(self):
        self.hla.expand = 'user'
        self.hla.save()

        response = self.client.get(self.get_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(isinstance(response.data['objects'][1]['user'], dict))
        self.assertTrue(response.data['objects'][1]['user']['id'], self.user.pk)
        self.assertIn('profile', response.data['objects'][1]['user'])
        self.assertEqual(response.data['objects'][0]['user'], None)

    def test_run_with_expand_and_fields(self):
        self.hla.fields = 'field3'
        self.hla.expand = 'ref'
        self.hla.save()
        response = self.client.get(self.get_url)
        self.assertEqual(list(response.data['objects'][0].keys()), ['field3'])
