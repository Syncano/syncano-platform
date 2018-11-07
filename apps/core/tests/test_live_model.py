# coding=UTF8
from unittest import mock

from django.db import models
from django.test import TestCase, override_settings
from django_dynamic_fixture import G

from ..abstract_models import LiveAbstractModel


class LiveModel(LiveAbstractModel):
    value = models.CharField(max_length=128)


class LiveWithUniqueModel(LiveAbstractModel):
    value = models.CharField(max_length=128)

    class Meta:
        unique_together = ('value', '_is_live')


class TestLiveModel(TestCase):
    def setUp(self):
        self.live_object = G(LiveModel)

    def test_live_field(self):
        field = LiveModel._meta.get_field('_is_live')
        self.assertTrue(field.db_index)
        self.assertFalse(field.unique)

    def test_soft_delete(self):
        self.live_object.soft_delete()
        self.assertFalse(self.live_object.is_live)
        self.assertTrue(LiveModel.all_objects.dead().exists())
        self.assertFalse(LiveModel.all_objects.live().exists())
        self.assertFalse(LiveModel.objects.exists())

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_soft_delete_is_processed(self):
        self.live_object.soft_delete()
        self.assertFalse(LiveModel.all_objects.dead().exists())
        self.assertFalse(LiveModel.all_objects.live().exists())
        self.assertFalse(LiveModel.objects.exists())

    @mock.patch('apps.core.abstract_models.LiveAbstractModel.soft_delete', mock.Mock())
    def test_if_default_delete_is_soft(self):
        self.live_object.delete()
        self.assertTrue(self.live_object.soft_delete.called)

    def test_hard_delete(self):
        self.live_object.hard_delete()
        self.assertFalse(LiveModel.all_objects.dead().exists())
        self.assertFalse(LiveModel.all_objects.live().exists())
        self.assertFalse(LiveModel.objects.exists())

    def test_if_manager_delete_is_a_hard_one(self):
        LiveModel.objects.filter(pk=self.live_object.pk).delete()
        self.assertFalse(LiveModel.all_objects.dead().exists())
        self.assertFalse(LiveModel.all_objects.live().exists())
        self.assertFalse(LiveModel.objects.exists())


class TestLiveWithUniqueModel(TestCase):
    def setUp(self):
        self.live_object = G(LiveWithUniqueModel)

    def test_live_field(self):
        field = self.live_object._meta.get_field('_is_live')
        self.assertFalse(field.db_index)
        self.assertFalse(field.unique)
