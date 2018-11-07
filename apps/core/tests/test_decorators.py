# coding=UTF8
from unittest import mock

from django.test import TestCase

from apps.core.decorators import cached
from apps.core.tests.mixins import CleanupTestCaseMixin

mock_func = mock.MagicMock()


@cached
def cached_func(x):
    mock_func()
    return x


@cached(timeout=15)
def cached_func_with_timeout(x):
    mock_func()
    return x


class TestCachedDecorator(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        mock_func.reset_mock()

    def test_global_cached_function(self):
        self.assertEqual(cached_func(15), 15)
        self.assertTrue(mock_func.called)

        mock_func.reset_mock()
        self.assertEqual(cached_func(15), 15)
        self.assertFalse(mock_func.called)

    def test_global_cached_function_with_timeout(self):
        self.assertEqual(cached_func_with_timeout(15), 15)
        self.assertTrue(mock_func.called)

        mock_func.reset_mock()
        self.assertEqual(cached_func_with_timeout(15), 15)
        self.assertFalse(mock_func.called)
