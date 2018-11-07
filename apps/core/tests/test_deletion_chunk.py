# coding=UTF8
from unittest import mock

from django.db import models
from django.test import TestCase
from django_dynamic_fixture import G

from apps.core.tests.mixins import CleanupTestCaseMixin


class ModelA(models.Model):
    pass


class ModelB(models.Model):
    ref = models.ForeignKey(ModelA, on_delete=models.CASCADE)


class ModelC(models.Model):
    ref = models.ForeignKey(ModelB, on_delete=models.CASCADE)


class TestDeletionChunk(CleanupTestCaseMixin, TestCase):
    @mock.patch('apps.core.appconfig.DELETION_MAX_CHUNK', 2)
    def test_chunked_deletion(self):
        obj_a = G(ModelA)
        G(ModelC, ref=G(ModelB, ref=obj_a))
        G(ModelC, ref=G(ModelB, ref=obj_a))
        self.assertTrue(ModelC.objects.exists())

        # Process chunked deletion of ModelB and standard deletion of ModelA and ModelC
        obj_a.delete()
        self.assertFalse(ModelC.objects.exists())
