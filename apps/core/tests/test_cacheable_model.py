# coding=UTF8
from unittest import mock

from django.db import models
from django.test import TestCase, override_settings
from django_dynamic_fixture import G

from apps.core.helpers import Cached
from apps.core.tests.mixins import CleanupTestCaseMixin

from ..abstract_models import CacheableAbstractModel


class CacheableModel(CacheableAbstractModel):
    value = models.CharField(max_length=128)


class CacheableSyncModel(CacheableAbstractModel):
    SYNC_INVALIDATION = True
    value = models.CharField(max_length=128)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestCacheableModel(CleanupTestCaseMixin, TestCase):
    def test_automatic_invalidation_on_update(self):
        obj = G(CacheableModel, value='initial')
        obj_cached = Cached(CacheableModel, kwargs={'pk': obj.pk}).get()
        self.assertEqual(obj_cached.value, obj.value)

        obj.value = 'new'
        obj.save()
        obj_cached = Cached(CacheableModel, kwargs={'pk': obj.pk}).get()
        self.assertEqual(obj_cached.value, obj.value)

    def test_automatic_invalidation_on_delete(self):
        self.assertRaises(CacheableModel.DoesNotExist, Cached(CacheableModel, kwargs={'pk': 1}).get)

        obj = G(CacheableModel, value='initial')
        obj_pk = obj.pk
        obj_cached = Cached(CacheableModel, kwargs={'pk': obj_pk}).get()
        self.assertEqual(obj_cached.value, obj.value)

        obj.delete()
        self.assertRaises(CacheableModel.DoesNotExist, Cached(CacheableModel, kwargs={'pk': obj_pk}).get)

    @mock.patch('apps.core.tasks.SyncInvalidationTask')
    @override_settings(LOCATIONS=['dev', 'test'])
    def test_sync_invalidation(self, task_mock):
        obj = G(CacheableSyncModel, value='initial')
        obj_cached = Cached(CacheableSyncModel, kwargs={'pk': obj.pk}).get()
        self.assertEqual(obj_cached.value, obj.value)
        self.assertFalse(task_mock.delay.called)

        obj.value = 'new'
        obj.save()

        self.assertTrue(task_mock.delay.called)
        version_key = Cached(CacheableSyncModel).get_version_key(obj)
        task_mock.delay.assert_called_with(version_key)
