from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from apps.billing.serializers import StripeSerializer
from apps.billing.viewsets import GenericStripeViewSet


class DummyStripeSerializer(StripeSerializer):

    class Meta:
        resource = mock.Mock
        api_key = '1234'


class DummyGenericStripeViewSet(GenericStripeViewSet):
    serializer_class = DummyStripeSerializer
    resource = mock.Mock
    expand = ['a']


class GenericStripeAPIViewTestCase(TestCase):

    def setUp(self):
        self.view = DummyGenericStripeViewSet()
        self.view.kwargs = {}
        self.view.request = mock.Mock(QUERY_PARAMS={})

    @mock.patch('apps.billing.generics.GenericStripeAPIView.get_resource')
    def test_get_object(self, get_resource_mock):
        self.assertFalse(get_resource_mock.called)
        self.view.get_resource(1, a=1, b=2)
        self.assertTrue(get_resource_mock.called)
        get_resource_mock.assert_called_once_with(1, a=1, b=2)

    def test_get_resource(self):
        resource = self.view.get_resource()
        self.assertEqual(resource, DummyGenericStripeViewSet.resource)

    def test_empty_resource(self):
        with self.assertRaises(ImproperlyConfigured):
            self.view.resource = None
            self.view.get_resource()

    def test_invalid_lookup_in_retrieve_resource(self):
        with self.assertRaises(ImproperlyConfigured):
            self.view.retrieve_resource()

    @mock.patch('apps.billing.generics.GenericStripeAPIView.filter_resource')
    def test_invalid_expand_in_retrieve_resource(self, filter_resource_mock):
        self.view.kwargs['pk'] = 10
        self.view.expand = 'not a list or tuple'
        self.assertFalse(filter_resource_mock.called)
        with self.assertRaises(ImproperlyConfigured):
            self.view.retrieve_resource()
        self.assertTrue(filter_resource_mock.called)

    @mock.patch('apps.billing.generics.GenericStripeAPIView.get_resource')
    @mock.patch('apps.billing.generics.GenericStripeAPIView.check_object_permissions')
    def test_retrieve_resource(self, permissions_mock, get_resource_mock):
        self.view.kwargs['pk'] = 10
        get_resource_mock.return_value = get_resource_mock

        self.assertFalse(get_resource_mock.called)
        self.assertFalse(get_resource_mock.retrieve.called)
        self.assertFalse(permissions_mock.called)
        self.view.retrieve_resource()
        self.assertTrue(get_resource_mock.called)
        self.assertTrue(get_resource_mock.retrieve.called)
        self.assertTrue(permissions_mock.called)
        get_resource_mock.retrieve.assert_called_once_with(10, expand=['a'])

    def test_filter_resource(self):
        self.assertEqual(self.view.filter_resource(), {})
