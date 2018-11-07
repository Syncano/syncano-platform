from unittest import mock

from django.db import models
from django.test import TestCase
from django_dynamic_fixture import G

from apps.core.abstract_models import LiveAbstractModel
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance

from ..tasks import DeleteLiveObjectTask


class TestModel(LiveAbstractModel):
    value = models.CharField(max_length=128)


class TestNotLiveModel(models.Model):
    value = models.CharField(max_length=128)


class TestDeleteObjectTask(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.instance = G(Instance, name='testinstance')
        set_current_instance(self.instance)

        self.test_object = G(TestModel)
        self.model_class_name = '%s.%s' % (TestModel._meta.app_label, TestModel._meta.model_name)

    def test_deleting_without_instance(self):
        DeleteLiveObjectTask.delay(model_class_name=self.model_class_name, object_pk=self.test_object.pk)
        self.assertFalse(TestModel.all_objects.exists())

    def test_deleting_with_instance(self):
        with mock.patch('apps.core.tasks.set_current_instance', mock.Mock()) as mock_method:
            DeleteLiveObjectTask.delay(model_class_name=self.model_class_name, object_pk=self.test_object.pk,
                                       instance_pk=self.instance.pk)
            self.assertTrue(mock_method.called)
        self.assertFalse(TestModel.all_objects.exists())

    def test_lookup_fails_for_incorrect_model(self):
        for model_class_name in ('wrong.completely', 'core.wrong'):
            self.assertRaises(LookupError, DeleteLiveObjectTask.delay,
                              model_class_name=model_class_name, object_pk=self.test_object.pk,
                              instance_pk=self.instance.pk)
        self.assertTrue(TestModel.all_objects.exists())


class TestIncorrectlyUsedDeleteObjectTask(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.test_object = G(TestNotLiveModel)
        self.model_class_name = '%s.%s' % (TestNotLiveModel._meta.app_label, TestNotLiveModel._meta.model_name)

    def test_unhandled_error_quits(self):
        self.assertRaises(AttributeError, DeleteLiveObjectTask.delay,
                          model_class_name=self.model_class_name, object_pk=self.test_object.pk)
        self.assertTrue(TestNotLiveModel.objects.exists())

    def test_task_with_nonexistent_instance(self):
        DeleteLiveObjectTask.delay(model_class_name=self.model_class_name, object_pk=self.test_object.pk,
                                   instance_pk=1337)
        self.assertTrue(TestNotLiveModel.objects.exists())
