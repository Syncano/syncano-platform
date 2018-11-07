# coding=UTF8
import csv
import io

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.data.models import DataObject, Klass
from apps.high_level.models import DataObjectHighLevelApi
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance
from apps.response_templates import models
from apps.response_templates.models import (
    RESPONSE_TEMPLATE_GET_ARG_NAMES,
    RESPONSE_TEMPLATE_HEADER_NAMES,
    ResponseTemplate
)
from apps.response_templates.predefined_templates import PredefinedTemplates
from apps.users.models import User


class TestResponseTemplatesRenderer(CleanupTestCaseMixin, APITestCase):

    def setUp(self):
        self.admin = G(Admin, is_active=True)
        instance_data = {'name': 'testinstance', 'description': 'testdesc', 'owner': self.admin}

        self.instance = G(Instance, **instance_data)
        self.admin.add_to_instance(self.instance)
        self.apikey = self.instance.create_apikey(allow_user_create=True)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key

        set_current_instance(self.instance)
        self._create_user_data()
        self._prepare_test_templates_and_data()

    def _create_user_data(self):
        self.user = User(username='john@doe.com')
        self.user.set_password('test')
        self.user.save()

        self.client.defaults['HTTP_X_USER_KEY'] = self.user.key

    def _prepare_test_templates_and_data(self):
        self.klass1 = G(Klass, schema=[{'name': 'a', 'type': 'string'}], name='test1', description='test1')
        self.klass2 = G(Klass, schema=[{'name': 'a', 'type': 'string', 'filter_index': True},
                                       {'name': 'expand_1', 'type': 'reference', 'target': 'test1'}],
                        name='test2', description='test2')

        self.data = {
            'name': 'template',
            'content': '<div>{{ user }};{{ instance }};{{ one }};{{ two }};</div>',
            'content_type': 'text/html',
            'context': {'one': 1, 'two': 2},
        }
        self.response_template = G(ResponseTemplate, **self.data)

        self.response_data = {
            'name': 'data_template',
            'content': """<div>{{ user }};{{ instance }};{{ one }};{{ two }};
{% for klass in response.objects %}{{ klass.name }};{% endfor %}</div>""",
            'content_type': 'text/html',
            'context': {'one': 1, 'two': 2},
        }
        self.response_data_template = G(ResponseTemplate, **self.response_data)

        self.render_endpoint_url = reverse('v1:response-templates-render', args=(self.instance.name,
                                                                                 self.response_template.name))
        self.klass_list_endpoint_url = reverse('v1:klass-list', args=(self.instance.name,))

        fail_template = {
            'name': 'fail_template',
            'content': '{{ some_object.gimme_this }}',
            'content_type': 'application/json',
            'context': {'one': 1, 'two': 2},
        }
        self.fail_template = G(ResponseTemplate, **fail_template)

    def test_render_with_header(self):
        for headers in self._get_template_name_list_data('template', RESPONSE_TEMPLATE_HEADER_NAMES):
            response = self.client.post(self.render_endpoint_url, **headers)
            self._assert_valid_response(response)

    def test_render_with_query_param(self):
        for params in self._get_template_name_list_data('template', RESPONSE_TEMPLATE_GET_ARG_NAMES):
            response = self.client.post(self.render_endpoint_url, params=params)
            self._assert_valid_response(response)

    def test_render_with_render_endpoint(self):
        response = self.client.post(self.render_endpoint_url)
        self._assert_valid_response(response)

    def test_render_with_render_data_endpoint(self):
        data = {'context': {'one': 11, 'two': 12}}
        response = self.client.post(self.render_endpoint_url, data=data)
        self._assert_valid_response(response, one=11, two=12)

    def test_render_with_restricted_fields(self):
        data = {'context': {'action': 'detail', 'one': 11, 'two': 12}}
        response = self.client.post(self.render_endpoint_url, data=data)
        self._assert_valid_response(response, one=11, two=12)

    def test_render_on_another_endpoint(self):
        for headers in self._get_template_name_list_data('data_template', RESPONSE_TEMPLATE_HEADER_NAMES):
            response = self.client.get(self.klass_list_endpoint_url, **headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(
                response.content.decode().replace('\n', ''),
                '<div>{user_username};{instance_name};{one};{two};{klass0_name};{klass1_name};'
                '{klass2_name};</div>'.format(
                    user_username=self.user.username,
                    instance_name=self.instance.name,
                    one=1,
                    two=2,
                    klass0_name='user_profile',  # a user profile class name
                    klass1_name='test1',
                    klass2_name='test2',
                )
            )
            self.assertEqual('text/html; charset=utf-8', response['content-type'])

    def test_application_json_content_type(self):
        response_json_data = {
            'name': 'json_data_template',
            'content': '{"one": {{ one }}}',
            'content_type': 'application/json',
            'context': {'one': 1, 'two': 2},
        }
        G(ResponseTemplate, **response_json_data)

        # totally overwrites the klass list endpoint results
        for headers in self._get_template_name_list_data('json_data_template', RESPONSE_TEMPLATE_HEADER_NAMES):
            response = self.client.get(self.klass_list_endpoint_url, **headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.content, b'{"one": 1}')
            self.assertEqual('application/json; charset=utf-8', response['content-type'])

    def test_template_that_can_not_be_rendered(self):
        render_endpoint_url = reverse('v1:response-templates-render',
                                      args=(self.instance.name, self.fail_template.name))
        response = self.client.post(render_endpoint_url)
        # raise UndefinedError
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'some_object', response.content)

        # raise AttributeError
        self.fail_template.content = '{{ True() }}'
        self.fail_template.save()
        response = self.client.post(render_endpoint_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'bool', response.content)

    def test_template_that_can_not_be_rendered_on_other_endpoint(self):
        for headers in self._get_template_name_list_data(self.fail_template.name, RESPONSE_TEMPLATE_HEADER_NAMES):
            response = self.client.get(self.klass_list_endpoint_url, **headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_not_matching_template_name(self):
        for headers in self._get_template_name_list_data('not_exsiting_template', RESPONSE_TEMPLATE_HEADER_NAMES):
            response = self.client.get(self.klass_list_endpoint_url, **headers)
            self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    def test_jinja2_environment_security(self):
        env_template_data = {
            'name': 'env_template',
            'content':
                "{{a.__class__.__base__.__subclasses__()[59]()._module.__builtins__['__import__']('os').environ}}",
            'content_type': 'application/json',
            'context': {'a': {}},
        }
        env_template = G(ResponseTemplate, **env_template_data)
        render_endpoint_url = reverse('v1:response-templates-render', args=(self.instance.name, env_template.name))

        response = self.client.post(render_endpoint_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_render_default_response_template(self):
        for template in PredefinedTemplates.templates:
            for headers in self._get_template_name_list_data(template['name'], RESPONSE_TEMPLATE_HEADER_NAMES):
                response = self.client.get(self.klass_list_endpoint_url, **headers)
                if template['name'] == 'objects_csv':
                    csv_content = csv.reader(io.StringIO(response.content.decode()))
                    user_profile_found = False
                    for line in csv_content:
                        self.assertTrue(len(line) > 0)  # check if not empty lines is rendered;
                        # we should always have hera a user profile class - check this;
                        if 'user_profile' in line:
                            user_profile_found = True
                    self.assertTrue(user_profile_found)

                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_infinite_loop_template_raise_timeout_exception(self):
        models.RESPONSE_TEMPLATE_CPU_SOFT_TIME_LIMIT = 1
        models.RESPONSE_TEMPLATE_CPU_HARD_TIME_LIMIT = 1  # we do not want wait for too long;
        infinite_loop_template_data = {
            'name': 'infinite_loop_template',
            'content': '{% for object in objects %}{{ objects.append(1) }}{% endfor %}',
            'content_type': 'application/json',
            'context': {'objects': [1, 2, 3, 4, 5]}
        }
        infinite_loop_template = G(ResponseTemplate, **infinite_loop_template_data)
        render_endpoint_url = reverse('v1:response-templates-render', args=(self.instance.name,
                                                                            infinite_loop_template.name))
        response = self.client.post(render_endpoint_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_on_endpoint_that_not_support_rendering(self):
        url = reverse('v1.1:endpoints', args=(self.instance.name,))
        for headers in self._get_template_name_list_data('data_template', RESPONSE_TEMPLATE_HEADER_NAMES):
            response = self.client.get(url, **headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_render_on_endpoints_data(self):
        # prepare data
        object1 = G(DataObject, _klass=self.klass1, _data={
            '1_a': 'a',
        })
        G(DataObject, _klass=self.klass2, _data={
            '1_a': 'test',
            '1_expand_2': object1.pk
        })
        G(DataObject, _klass=self.klass2, _data={
            '1_a': 'test22',
        })

        hla = G(DataObjectHighLevelApi, klass=self.klass2, expand='expand_2', excluded_fields='a', name='test',
                query={'a': {'_eq': 'test'}})

        # make test
        url = reverse('v1.1:hla-objects-get', args=[self.instance.name, hla.name])
        for headers in self._get_template_name_list_data('objects_html_table', RESPONSE_TEMPLATE_HEADER_NAMES):
            response = self.client.get(url, **headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual('text/html; charset=utf-8', response['content-type'])

    def _build_response_for_assert(self, one=1, two=2):
        return '<div>{user_username};{instance_name};{one};{two};</div>'.format(
            user_username=self.user.username, instance_name=self.instance.name, one=one, two=two
        ).encode()

    def _assert_valid_response(self, response, one=1, two=2):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, self._build_response_for_assert(one=one, two=two))
        self.assertEqual('text/html; charset=utf-8', response['content-type'])

    def _get_template_name_list_data(self, template_name, attributes_list):
        return [{key: template_name} for key in attributes_list]
