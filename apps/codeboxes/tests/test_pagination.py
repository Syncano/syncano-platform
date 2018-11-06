# coding=UTF8
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.codeboxes.models import CodeBox, CodeBoxTrace
from apps.codeboxes.runtimes import LATEST_PYTHON_RUNTIME
from apps.data.tests.test_pagination import TestPaginationMixin


class TestStandardPagination(TestPaginationMixin):
    def setUp(self):
        super().setUp()
        codebox = G(CodeBox, label='test', runtime_name=LATEST_PYTHON_RUNTIME,
                    source="print(ARGS)")

        for _ in range(5):
            CodeBoxTrace.create(codebox=codebox, executed_by_staff=False)
        self.url = reverse('v2:codebox-trace-list', args=(self.instance.name, codebox.id,))

    def test_if_page_size_works(self):
        self.check_pagination_url(self.url, {'page_size': 2}, objects_len=2)
        self.check_pagination_url(self.url, objects_len=5)

    def test_paginating_flow(self):
        response = self.check_pagination_url(self.url, {'page_size': 2, 'ordering': 'asc'}, objects_len=2,
                                             prev_exists=False,
                                             next_exists=True)
        self.assertEqual(response.data['objects'][0]['id'], 1)

        response = self.check_pagination_url(response.data['next'], objects_len=2, prev_exists=True, next_exists=True)
        self.assertEqual(response.data['objects'][0]['id'], 3)

        response = self.check_pagination_url(response.data['next'], objects_len=1, prev_exists=True, next_exists=False)
        self.assertEqual(response.data['objects'][0]['id'], 5)

        response = self.check_pagination_url(response.data['prev'], objects_len=2, prev_exists=True, next_exists=True)
        self.assertEqual(response.data['objects'][0]['id'], 3)

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

    def test_paginating_desc_flow(self):
        response = self.check_pagination_url(self.url, {'page_size': 2, 'ordering': 'desc'},
                                             objects_len=2, prev_exists=False, next_exists=True)
        self.assertEqual(response.data['objects'][0]['id'], 5)

        response = self.check_pagination_url(response.data['next'], objects_len=2, prev_exists=True, next_exists=True)
        self.assertEqual(response.data['objects'][0]['id'], 3)

        response = self.check_pagination_url(response.data['next'], objects_len=1, prev_exists=True, next_exists=False)
        self.assertEqual(response.data['objects'][0]['id'], 1)

        response = self.check_pagination_url(response.data['prev'], objects_len=2, prev_exists=True, next_exists=True)
        self.assertEqual(response.data['objects'][0]['id'], 3)
