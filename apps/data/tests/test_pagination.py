from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import DataObject, Klass
from apps.instances.helpers import set_current_instance


class TestPaginationMixin(SyncanoAPITestBase):
    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

    def check_pagination_url(self, url, params=None, code=status.HTTP_200_OK, objects_len=None, prev_exists=None,
                             next_exists=None):
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, code)
        if objects_len is not None:
            self.assertEqual(len(response.data['objects']), objects_len)
        for assert_is_none, key in ((prev_exists, 'prev'), (next_exists, 'next')):
            if assert_is_none is not None:
                if assert_is_none:
                    self.assertIsNotNone(response.data[key])
                else:
                    self.assertIsNone(response.data[key])
        return response


class TestStandardPagination(TestPaginationMixin):
    def setUp(self):
        super().setUp()

        for i in range(5):
            G(Klass, schema=[{'name': 'a', 'type': 'string'}],
              description='test', name='test%d' % (i + 1))
        self.url = reverse('v1:klass-list', args=(self.instance.name,))

    def test_if_page_size_works(self):
        self.check_pagination_url(self.url, {'page_size': 2}, objects_len=2)
        self.check_pagination_url(self.url, objects_len=5)

    def test_v2_page_size(self):
        url = reverse('v2:klass-list', args=(self.instance.name,))
        self.check_pagination_url(url, {'page_size': 2})

    def test_paginating_flow(self):
        response = self.check_pagination_url(self.url, {'page_size': 2}, objects_len=2, prev_exists=False,
                                             next_exists=True)
        self.assertEqual(response.data['objects'][0]['name'], 'test1')

        response = self.check_pagination_url(response.data['next'], objects_len=2, prev_exists=True, next_exists=True)
        self.assertEqual(response.data['objects'][0]['name'], 'test3')

        response = self.check_pagination_url(response.data['next'], objects_len=1, prev_exists=True, next_exists=False)
        self.assertEqual(response.data['objects'][0]['name'], 'test5')

        response = self.check_pagination_url(response.data['prev'], objects_len=2, prev_exists=True, next_exists=True)
        self.assertEqual(response.data['objects'][0]['name'], 'test3')

    def test_paginating_going_over_the_page_size_backwards(self):
        response = self.check_pagination_url(self.url, {'page_size': 2}, objects_len=2)
        first_page_data = response.data['objects']
        response = self.check_pagination_url(response.data['next'], prev_exists=True, next_exists=True)
        response = self.check_pagination_url(response.data['prev'], prev_exists=True, next_exists=True)
        self.assertEqual(first_page_data, response.data['objects'])

    def test_paginating_empty_when_page_size_not_reached(self):
        self.check_pagination_url(self.url, {'order_by': 'created_at'}, prev_exists=False, next_exists=False)

    def test_passing_invalid_type_direction_fails(self):
        self.check_pagination_url(self.url, {'direction': 'abcde'}, code=status.HTTP_400_BAD_REQUEST)

    def test_passing_wrong_value_direction_fails(self):
        self.check_pagination_url(self.url, {'direction': 2}, code=status.HTTP_400_BAD_REQUEST)

    def test_validation_of_pk_value(self):
        self.check_pagination_url(self.url, {'direction': 0, 'last_pk': -1}, code=status.HTTP_400_BAD_REQUEST)

    def test_paginating_desc_flow(self):
        response = self.check_pagination_url(self.url, {'page_size': 2, 'ordering': 'desc'},
                                             objects_len=2, prev_exists=False, next_exists=True)
        self.assertEqual(response.data['objects'][0]['name'], 'test5')

        response = self.check_pagination_url(response.data['next'], objects_len=2, prev_exists=True, next_exists=True)
        self.assertEqual(response.data['objects'][0]['name'], 'test3')

        response = self.check_pagination_url(response.data['next'], objects_len=1, prev_exists=True, next_exists=False)
        self.assertEqual(response.data['objects'][0]['name'], 'test1')

        response = self.check_pagination_url(response.data['prev'], objects_len=2, prev_exists=True, next_exists=True)
        self.assertEqual(response.data['objects'][0]['name'], 'test3')


class TestAdditionalPagination(TestPaginationMixin):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        self.klass = G(Klass, schema=[{'name': 'fl', 'type': 'float', 'order_index': True}],
                       description='test', name='test1')
        DataObject._meta.get_field('_data').reload_schema(None)
        for i in range(5):
            G(DataObject, _klass=self.klass, _data={'1_fl': str(1 / (10 - i))}, _files={})

        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_paginating_by_float(self):
        self.check_pagination_url(self.url, {'order_by': 'fl', 'page_size': 1}, code=status.HTTP_200_OK)


class TestKeySetPagination(TestPaginationMixin):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        self.klass = G(Klass, schema=[{'name': 'a_Ordered', 'type': 'string', 'order_index': True},
                                      {'name': 'a', 'type': 'string'}],
                       description='test', name='test1')
        DataObject._meta.get_field('_data').reload_schema(None)
        for i in range(5):
            G(DataObject, _klass=self.klass, _data={'1_a': str(i), '1_a_Ordered': str(i)}, _files={})

        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_if_ordering_by_unindexed_field_fails(self):
        self.check_pagination_url(self.url, {'order_by': 'a'}, code=status.HTTP_400_BAD_REQUEST)

    def test_if_ordering_by_custom_field_asc_works(self):
        response = self.client.get(self.url, {'order_by': 'a_Ordered'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(response.data['objects'][0]['a_Ordered'], response.data['objects'][-1]['a_Ordered'])

    def test_if_ordering_by_custom_field_desc_works(self):
        response = self.client.get(self.url, {'order_by': '-a_Ordered'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['objects'][0]['a_Ordered'], response.data['objects'][-1]['a_Ordered'])

    def test_if_page_size_works(self):
        self.check_pagination_url(self.url, {'page_size': 2, 'order_by': 'created_at'}, objects_len=2)
        self.check_pagination_url(self.url, {'page_size': 5, 'order_by': 'created_at'}, objects_len=5)

    def test_paginating_by_desc_id(self):
        response = self.client.get(self.url, {'order_by': '-id'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['objects'][0]['id'], response.data['objects'][-1]['id'])

    def test_if_ordering_asc_works(self):
        response = self.client.get(self.url, {'order_by': 'created_at'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(response.data['objects'][0]['created_at'], response.data['objects'][-1]['created_at'])

    def test_if_ordering_desc_works(self):
        response = self.client.get(self.url, {'order_by': '-created_at'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['objects'][0]['created_at'], response.data['objects'][-1]['created_at'])

    def test_paginating_asc_flow(self):
        response = self.check_pagination_url(self.url, {'page_size': 2, 'order_by': 'created_at'}, objects_len=2,
                                             prev_exists=False, next_exists=True)
        response = self.check_pagination_url(response.data['next'], objects_len=2, prev_exists=True, next_exists=True)
        response = self.check_pagination_url(response.data['next'], objects_len=1, prev_exists=True, next_exists=False)
        self.check_pagination_url(response.data['prev'], objects_len=2, prev_exists=True, next_exists=True)

    def test_paginating_desc_flow(self):
        response = self.check_pagination_url(self.url, {'page_size': 2, 'order_by': '-created_at'}, objects_len=2,
                                             prev_exists=False, next_exists=True)
        response = self.check_pagination_url(response.data['next'], objects_len=2, prev_exists=True, next_exists=True)
        response = self.check_pagination_url(response.data['next'], objects_len=1, prev_exists=True, next_exists=False)
        self.check_pagination_url(response.data['prev'], objects_len=2, prev_exists=True, next_exists=True)

    def test_paginating_going_over_the_page_size_backwards(self):
        response = self.check_pagination_url(self.url, {'page_size': 2, 'order_by': 'created_at'}, objects_len=2,
                                             prev_exists=False, next_exists=True)
        first_page_data = response.data['objects']
        response = self.check_pagination_url(response.data['next'], prev_exists=True, next_exists=True)
        response = self.check_pagination_url(response.data['prev'], prev_exists=True, next_exists=True)
        self.assertEqual(first_page_data, response.data['objects'])

    def test_pagination_is_empty_when_page_size_not_reached(self):
        self.check_pagination_url(self.url, {'order_by': 'created_at'}, prev_exists=False, next_exists=False)

    def test_nonexisting_orderby_field(self):
        self.check_pagination_url(self.url, {'order_by': 'cr'}, code=status.HTTP_400_BAD_REQUEST)

    def test_incorrect_orderby_field(self):
        self.check_pagination_url(self.url, {'order_by': '_klass'}, code=status.HTTP_400_BAD_REQUEST)

    def test_paginating_falls_back_to_standard_without_orderby(self):
        response = self.check_pagination_url(self.url, {'page_size': 2}, objects_len=2, prev_exists=False,
                                             next_exists=True)
        response = self.check_pagination_url(response.data['next'])
        self.assertNotIn('last_value', response.data['next'])

    def test_paginating_by_pk_asc(self):
        response = self.check_pagination_url(self.url, {'page_size': 5, 'order_by': 'id'}, objects_len=5,
                                             next_exists=True, prev_exists=False)
        self.assertLess(response.data['objects'][0]['id'], response.data['objects'][-1]['id'])

    def test_paginating_by_pk_desc(self):
        response = self.check_pagination_url(self.url, {'page_size': 5, 'order_by': '-id'}, objects_len=5)
        self.assertGreater(response.data['objects'][0]['id'], response.data['objects'][-1]['id'])

    def test_validation_of_field_value(self):
        with mock.patch('apps.data.v1.views.ObjectViewSet.order_fields', new={'revision'}):
            response = self.client.get(self.url,
                                       {'order_by': 'revision', 'direction': 0, 'last_pk': 1, 'last_value': 2147483648})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestKeySetWithNullsPagination(TestPaginationMixin):
    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True, CREATE_INDEXES_CONCURRENTLY=False)
    def setUp(self):
        super().setUp()

        self.klass = G(Klass, schema=[{'name': 'a_Ordered', 'type': 'string', 'order_index': True}],
                       description='test', name='test1')
        DataObject._meta.get_field('_data').reload_schema(None)
        for i in range(3):
            G(DataObject, _klass=self.klass, _files={})
            G(DataObject, _klass=self.klass, _data={'1_a_Ordered': str(i)}, _files={})

        self.url = reverse('v1:dataobject-list', args=(self.instance.name, self.klass.name))

    def test_paginating_by_pk_asc(self):
        response = self.check_pagination_url(self.url, {'page_size': 4, 'order_by': 'a_Ordered'}, objects_len=4,
                                             next_exists=True)
        self.assertIsNotNone(response.data['objects'][-2]['a_Ordered'])
        self.assertIsNone(response.data['objects'][-1]['a_Ordered'])
        first_page_objects = response.data['objects']

        response = self.check_pagination_url(response.data['next'], objects_len=2)
        self.assertLess(response.data['objects'][0]['id'], response.data['objects'][1]['id'])

        response = self.check_pagination_url(response.data['prev'], objects_len=4)
        self.assertEqual(first_page_objects, response.data['objects'])

    def test_paginating_by_pk_desc(self):
        response = self.check_pagination_url(self.url, {'page_size': 4, 'order_by': '-a_Ordered'}, objects_len=4,
                                             next_exists=True)
        self.assertIsNone(response.data['objects'][0]['a_Ordered'])
        self.assertIsNotNone(response.data['objects'][3]['a_Ordered'])
        first_page_objects = response.data['objects']

        response = self.check_pagination_url(response.data['next'], objects_len=2)
        self.assertGreater(response.data['objects'][0]['id'], response.data['objects'][1]['id'])

        response = self.check_pagination_url(response.data['prev'], objects_len=4)
        self.assertEqual(first_page_objects, response.data['objects'])
