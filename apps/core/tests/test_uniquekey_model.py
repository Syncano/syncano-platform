# coding=UTF8
from unittest import mock

from django.db import IntegrityError, models, transaction
from django.test import TestCase

from ..abstract_models import UniqueKeyAbstractModel


class UniqueKeyModel(UniqueKeyAbstractModel):
    value = models.CharField(max_length=128)


class UniqueKeyWithChangedKeyModel(UniqueKeyAbstractModel):
    KEY_FIELD_NAME = 'super_key'
    KEY_FIELD_KWARGS = {}


class TestUniqueKeyModel(TestCase):
    @mock.patch('apps.core.abstract_models.UniqueKeyAbstractModel.generate_key', side_effect=['a', 'a', 'a', 'b'])
    def test_collision_handling_retries(self, mock_func):
        with transaction.atomic():
            UniqueKeyModel().save()
        with transaction.atomic():
            UniqueKeyModel().save()
        self.assertEqual(mock_func.call_count, 4)

    @mock.patch('apps.core.abstract_models.UniqueKeyAbstractModel.generate_key', return_value='a')
    def test_collision_handling_fails_after_retries(self, mock_func):
        with transaction.atomic():
            UniqueKeyModel().save()
        self.assertRaises(IntegrityError, UniqueKeyModel().save)

    def test_uniquekey_gets_saved_properly(self):
        UniqueKeyModel().save()
        self.assertTrue(UniqueKeyModel.objects.exists())

    def test_if_can_be_updated_without_key_change(self):
        test_model = UniqueKeyModel()
        test_model.save()
        old_key = test_model.key
        test_model.value = 'new value'
        test_model.save()
        self.assertEqual(test_model.key, old_key)

    def test_if_can_be_reset(self):
        test_model = UniqueKeyModel()
        test_model.save()
        old_key = test_model.key
        test_model.reset()
        self.assertNotEqual(test_model.key, old_key)

    def test_if_key_settings_are_respected(self):
        key_name = UniqueKeyModel.KEY_FIELD_NAME
        test_model = UniqueKeyModel()
        self.assertTrue(test_model._meta.get_field(key_name).unique)

        key_name = UniqueKeyWithChangedKeyModel.KEY_FIELD_NAME
        test_model = UniqueKeyWithChangedKeyModel
        self.assertFalse(test_model._meta.get_field(key_name).unique)
