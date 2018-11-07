# coding=UTF8
from django.conf import settings
from django.test import tag
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.codeboxes.models import CodeBox
from apps.codeboxes.runtimes import LATEST_PYTHON_RUNTIME
from apps.codeboxes.tests.test_codebox_api import (
    CodeBoxTestBase,
    TestScheduleFromSocketDetail,
    TestScriptFromSocketDetail
)


@tag('legacy_codebox')
class TestTracesAPI(CodeBoxTestBase):
    def test_getting_long_trace(self):
        codebox = G(CodeBox, label='test', runtime_name=LATEST_PYTHON_RUNTIME,
                    source="print(ARGS)")
        url = reverse('v2:codebox-run', args=(self.instance.name, codebox.id))

        data = {'payload': {'a': 'a' * settings.CODEBOX_RESULT_CUTOFF}}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        trace_id = response.data['id']

        url = reverse('v2:codebox-trace-list', args=(self.instance.name, codebox.id,))
        response = self.client.get(url)
        # result should not be a part of a list
        self.assertNotIn('result', response.data['objects'][0])

        url = reverse('v2:codebox-trace-detail', args=(self.instance.name, codebox.id, trace_id))
        response = self.client.get(url)
        self.assertIn('result', response.data)
        self.assertIn(data['payload']['a'], response.data['result']['stdout'])


@tag('legacy_codebox')
class TestScriptFromSocketV2Detail(TestScriptFromSocketDetail):
    def setUp(self):
        super().setUp()

        self.edit_url = reverse('v2:codebox-detail', args=(self.instance.name, self.script.id,))
        self.run_url = reverse('v2:codebox-run', args=(self.instance.name, self.script.id,))

    def test_detail_with_socket(self):
        response = self.client.get(self.edit_url)
        self.assertIn('socket', response.data['links'])


@tag('legacy_codebox')
class TestScheduleFromSocketV2Detail(TestScheduleFromSocketDetail):
    def setUp(self):
        super().setUp()

        self.url = reverse('v2:codebox-schedule-detail', args=(self.instance.name, self.schedule.id,))

    def test_detail_with_socket(self):
        response = self.client.get(self.url)
        self.assertIn('socket', response.data['links'])
