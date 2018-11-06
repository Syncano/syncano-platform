from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APITransactionTestCase

from apps.admins.models import Admin
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance
from apps.users.models import Group, Membership, User
from apps.users.tests.test_user_api import UserTestCase

from ..models import Klass


class TestClassesDetailAPI(SyncanoAPITestBase):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'string'},
                                      {'name': 'int_indexed', 'type': 'integer',
                                       'order_index': True, 'filter_index': True},
                                      {'name': 'bool_unique', 'type': 'boolean',
                                       'unique': True}],
                       name='test',
                       description='test')
        self.url = reverse('v1:klass-detail', args=(self.instance.name, self.klass.name))

    def test_if_can_get_proper_klass(self):
        G(Klass, schema=[{'name': 'a', 'type': 'string'}], name='test2', description='test2')
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], self.klass.description)

    def test_if_getting_resource_is_case_insensitive(self):
        response = self.client.get(reverse('v1:klass-detail', args=(self.instance.name, self.klass.name.upper(),)))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], self.klass.description)

    def test_if_can_delete_class(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertFalse(Klass.objects.exists())

    def test_if_can_update_class_with_patch(self):
        data = {'description': 'test2'}

        response = self.client.patch(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_class = Klass.objects.get(id=self.klass.id)
        self.assertEqual(data['description'], updated_class.description)

    def test_if_can_update_class(self):
        data = {
            'description': 'test2',
            'schema': [{'name': 'a', 'type': 'string'}]
        }

        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(data['description'], response.data['description'])
        self.assertEqual(data['schema'], response.data['schema'])

    def test_if_adding_fields_to_schema_updates_mapping(self):
        schema = self.klass.schema
        schema.append({'name': 'b', 'type': 'string'})

        data = {'schema': schema}

        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        klass = Klass.objects.get(pk=self.klass.id)
        self.assertEqual(klass.mapping, {'a': '1_a', 'bool_unique': '1_bool_unique', 'b': '2_b',
                                         'int_indexed': '1_int_indexed'})
        self.assertIsNone(klass.index_changes)

    def test_missing_referenced_target_class_fails(self):
        schema = self.klass.schema
        schema.append({'name': 'ref2', 'type': 'reference', 'target': 'test2'})

        data = {'schema': schema}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def test_if_reading_fields_to_schema_updates_mapping(self):
        data = {'schema': [{'name': 'b', 'type': 'string'}]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        klass = Klass.objects.get(pk=self.klass.id)
        self.assertEqual(klass.mapping, {'b': '2_b'})

        data = {'schema': [{'name': 'a', 'type': 'string'}]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        klass = Klass.objects.get(pk=self.klass.id)
        self.assertEqual(klass.mapping, {'a': '3_a'})

    def test_if_changing_field_type_updates_mapping(self):
        data = {'schema': [{'name': 'a', 'type': 'boolean'}]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        klass = Klass.objects.get(pk=self.klass.id)
        self.assertEqual(klass.mapping, {'a': '2_a'})

    def test_if_mapping_is_properly_populated(self):
        data = {'schema': [{'name': 'A', 'type': 'STRING'}, {'name': 'B', 'type': 'StrinG'}]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        klass = Klass.objects.get(pk=self.klass.id)
        self.assertEqual(klass.mapping, {'A': '2_A', 'B': '2_B'})
        self.assertEqual(klass.schema, [{'name': 'A', 'type': 'string'}, {'name': 'B', 'type': 'string'}])

    @mock.patch('apps.data.signal_handlers.IndexKlassTask', mock.MagicMock())
    def test_klass_locks_after_index_change(self):
        data = {'schema': [{'name': 'a', 'type': 'string', 'order_index': True, 'filter_index': True}, ]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        klass = Klass.objects.get(pk=self.klass.id)
        self.assertEqual(klass.is_locked, True)

    @mock.patch('apps.data.validators.SchemaValidator.max_indexes_num', 16)
    @mock.patch('apps.data.signal_handlers.IndexKlassTask', mock.MagicMock())
    def test_processing_of_new_indexes(self):
        data = {'schema': [
            {'name': 'string', 'type': 'string', 'order_index': True, 'filter_index': True},
            {'name': 'text', 'type': 'text'},
            {'name': 'integer', 'type': 'integer', 'order_index': True, 'filter_index': True},
            {'name': 'float', 'type': 'float', 'order_index': True, 'filter_index': True},
            {'name': 'bool', 'type': 'boolean', 'order_index': True, 'filter_index': True},
            {'name': 'datetime', 'type': 'datetime', 'order_index': True, 'filter_index': True},
            {'name': 'file', 'type': 'file'},
            {'name': 'ref', 'type': 'reference', 'order_index': True, 'filter_index': True, 'target': 'self'}
        ]}

        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        klass = Klass.objects.get(pk=self.klass.id)
        expected_indexes_count = len(data['schema']) - 2
        self.assertEqual(len(klass.index_changes['filter']['+']), expected_indexes_count)
        self.assertEqual(len(klass.index_changes['order']['+']), expected_indexes_count)
        self.assertEqual(klass.schema, data['schema'])

    def test_instance_separation(self):
        G(Klass, schema=[{'name': 'a', 'type': 'string'}], name='test2', description='test2')
        admin = G(Admin, is_active=True)
        response = self.client.get(self.url, HTTP_X_API_KEY=admin.key)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_if_adding_unique_to_existing_field_fails(self):
        data = {'schema': [{'name': 'a', 'type': 'string', 'unique': True}]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_manipulating_klass_with_unique_index_works(self):
        data = {'schema': [{'name': 'a', 'type': 'string'},
                           {'name': 'bool_unique', 'type': 'boolean', 'unique': True, 'filter_index': True}]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        klass = Klass.objects.get(pk=self.klass.id)
        self.assertFalse(klass.index_changes)
        self.assertEqual(klass.schema, data['schema'])


class TestClassesDetailAPITransaction(CleanupTestCaseMixin, APITransactionTestCase):
    fixtures = ['core_data.json', ]

    def setUp(self):
        self.instance = G(Instance, name='testinstance', description='testdesc')
        self.admin = G(Admin, is_active=True)
        self.admin.add_to_instance(self.instance)
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
        super().setUp()
        set_current_instance(self.instance)
        self.klass = G(Klass, schema=[{'name': 'a', 'type': 'integer'}], name='test',
                       description='test')
        self.url = reverse('v1:klass-detail', args=(self.instance.name, self.klass.name))

    def tearDown(self):
        self.instance.delete()

    def test_klass_properly_unlocks_after_index_change(self):
        data = {'schema': [{'name': 'a', 'type': 'integer', 'order_index': True, 'filter_index': True}, ]}
        response = self.client.patch(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        klass = Klass.objects.get(pk=self.klass.id)
        self.assertEqual(klass.is_locked, False)


class TestClassesListAPI(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('v1:klass-list', args=(self.instance.name,))

    def test_if_can_create_class(self):
        data = {'name': 'TEST', 'description': 'test test',
                'schema': [{'name': 'a', 'type': 'integer'}]}

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], data['name'].lower())
        self.assertTrue(Klass.objects.filter(name=data['name']).exists())

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_creating_class_with_empty_schema(self):
        data = {'name': 'test', 'schema': []}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @mock.patch('apps.billing.models.AdminLimit.get_classes_count', mock.MagicMock(return_value=1))
    def test_if_can_create_after_limit_reached(self):
        data = {'name': 'test', 'description': 'test test',
                'schema': [{'name': 'a', 'type': 'integer'}]}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data['name'] = 'newclass'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_can_list_classes(self):
        set_current_instance(self.instance)
        G(Klass, schema=[{'name': 'a', 'type': 'integer'}], name='test', description='test')

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    @mock.patch('apps.data.validators.SchemaValidator.max_indexes_num', 16)
    @mock.patch('apps.data.signal_handlers.IndexKlassTask', mock.MagicMock())
    def test_processing_of_new_indexes_on_new_class(self):
        data = {
            'name': 'test', 'description': 'test test',
            'schema': [
                {'name': 'string', 'type': 'string', 'order_index': True, 'filter_index': True},
                {'name': 'text', 'type': 'text'},
                {'name': 'integer', 'type': 'integer', 'order_index': True, 'filter_index': True},
                {'name': 'float', 'type': 'float', 'order_index': True, 'filter_index': True},
                {'name': 'bool', 'type': 'boolean', 'order_index': True, 'filter_index': True},
                {'name': 'datetime', 'type': 'datetime', 'order_index': True, 'filter_index': True},
                {'name': 'file', 'type': 'file'},
                {'name': 'ref', 'type': 'reference', 'order_index': True, 'filter_index': True, 'target': 'self'}
            ]}
        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        klass = Klass.objects.get(name=data['name'])

        expected_indexes_count = len(data['schema']) - 2
        self.assertEqual(len(klass.index_changes['filter']['+']), expected_indexes_count)
        self.assertEqual(len(klass.index_changes['order']['+']), expected_indexes_count)
        self.assertEqual(klass.schema, data['schema'])


class TestUserProfileClass(UserTestCase):
    def setUp(self):
        super().init_data(access_as='admin')

    def test_if_user_profile_is_visible(self):
        response = self.client.get(reverse('v1:klass-list', args=(self.instance.name,)))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)

    def test_if_user_profile_is_protected_from_deletion(self):
        url = reverse('v1:klass-detail', args=(self.instance.name, Klass.USER_PROFILE_NAME))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestClassesFilteringByPermissions(UserTestCase):
    def setUp(self):
        super().init_data()

    def assert_klass_access(self, assert_denied=False, **kwargs):
        group_permissions = kwargs.pop('group_permissions', Klass.PERMISSIONS.NONE)
        other_permissions = kwargs.pop('other_permissions', Klass.PERMISSIONS.NONE)
        klass = G(Klass, schema=[{'name': 'a', 'type': 'string'}],
                  name='test',
                  description='test',
                  group_permissions=group_permissions,
                  other_permissions=other_permissions,
                  **kwargs)

        detail_response = self.client.get(reverse('v1:klass-detail', args=(self.instance.name, klass.name)))
        list_response = self.client.get(reverse('v1:klass-list', args=(self.instance.name,)))

        if assert_denied:
            self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(list_response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(list_response.data['objects']), 1)
        else:
            self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
            self.assertEqual(list_response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(list_response.data['objects']), 2)

    def test_if_getting_klass_without_permission_is_denied(self):
        self.assert_klass_access(assert_denied=True)

    def test_if_getting_klass_without_my_group_permissions_is_denied(self):
        self.assert_klass_access(assert_denied=True, group=G(Group), group_permissions=Klass.PERMISSIONS.READ)

    def test_if_can_get_klass_with_group_permissions(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        self.assert_klass_access(group=group, group_permissions=Klass.PERMISSIONS.READ)

    def test_if_can_get_klass_with_other_permissions(self):
        self.assert_klass_access(other_permissions=Klass.PERMISSIONS.READ)

    def test_if_only_one_class_is_returned(self):
        group = G(Group)
        G(Membership, user=self.user, group=group)
        G(Membership, user=G(User), group=group)
        # Expected count is 2 in listing as there is also a user_profile created at this point
        self.assert_klass_access(group=group, group_permissions=Klass.PERMISSIONS.READ,
                                 other_permissions=Klass.PERMISSIONS.READ)
