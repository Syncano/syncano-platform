# coding=UTF8
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.response_templates.models import ResponseTemplate
from apps.response_templates.predefined_templates import PredefinedTemplates


class TestResponseTemplatesAPI(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()

        set_current_instance(self.instance)

        self.data = {'name': 'test_response_template', 'content': '<div>Hello world!</div>',
                     'content_type': 'text/html', 'context': '{"one": 1}'}
        self.response_template = G(ResponseTemplate, **self.data)
        self.url = reverse('v1:response-templates-detail', args=(self.instance.name, self.response_template.name))
        self.list_url = reverse('v1:response-templates-list', args=(self.instance.name,))

    def test_list_retrieve(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_creating(self):
        self.data['name'] = 'test_response_template_1'  # name is unique
        response = self.client.post(self.list_url, data=self.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_updating(self):
        self.data['content'] = '<div>Hello again!</div>'
        response = self.client.put(self.url, data=self.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content'], '<div>Hello again!</div>')

    def test_updating_patch(self):
        response = self.client.patch(self.url, data={'content': '<div>Hello Put!</div>'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content'], '<div>Hello Put!</div>')

    def test_delete(self):
        response = self.client.delete(reverse('v1:response-templates-detail',
                                              args=(self.instance.name, self.response_template.name)))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_creating_with_disallowed_key(self):
        data = {'name': 'test_response_template_2', 'content': '<div>Hello world!</div>',
                'content_type': 'text/html', 'context': '{"response": 1}'}
        response = self.client.post(self.list_url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'response', response.content)

    def test_rename(self):
        new_name = 'new-name'
        url = reverse('v1:response-templates-rename', args=[self.instance.name, self.response_template.name])
        response = self.client.post(url, {'new_name': new_name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], new_name)

        url = reverse('v1:response-templates-detail', args=[self.instance.name, new_name])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_rename_is_validated(self):
        G(ResponseTemplate, name='new-name')
        url = reverse('v1:response-templates-rename', args=[self.instance.name, self.response_template.name])
        # Test already existing name
        response = self.client.post(url, {'new_name': 'new-name'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_default_template_response(self):
        for template in PredefinedTemplates.templates:
            url = reverse('v1:response-templates-detail', args=(self.instance.name, template['name']))
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
