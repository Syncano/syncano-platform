# coding=UTF8
from django.db import models
from django.test import TestCase
from django_dynamic_fixture import G

from apps.core.fields import DictionaryField

from ..abstract_models import TrackChangesAbstractModel


class VirtualFieldsTestModel(TrackChangesAbstractModel):
    name = models.CharField(max_length=128)

    schema = [
        {
            'name': 'bool_field',
            'class': 'BooleanField',
            'kwargs': {
                'default': False
            }
        }
    ]

    options = DictionaryField('options', schema=schema)


class ForeignKeyTestModel(TrackChangesAbstractModel):
    name = models.CharField(max_length=128)
    reference = models.ForeignKey('self', null=True, on_delete=models.CASCADE)


class DefinedFieldsTestModel(TrackChangesAbstractModel):
    TRACKED_FIELDS = ('name',)
    name = models.CharField(max_length=128)
    other_name = models.CharField(max_length=128)


class IgnoredFieldsTestModel(TrackChangesAbstractModel):
    IGNORED_FIELDS = ('name',)
    name = models.CharField(max_length=128)
    other_name = models.CharField(max_length=128)


class TestVirtualFieldTrackChangesModel(TestCase):
    def setUp(self):
        self.test_model = G(VirtualFieldsTestModel, name='my_name', options={})

    def test_whats_changed_populates_properly_for_standard_field(self):
        test_model = self.test_model
        self.assertEqual(test_model.whats_changed(), set())
        test_model.name = 'new_name'
        self.assertEqual(test_model.whats_changed(), {'name'})
        test_model.name = 'my_name'
        self.assertEqual(test_model.whats_changed(), set())

    def test_whats_changed_ignores_virtual_field(self):
        test_model = self.test_model
        test_model.name = 'new_name'
        test_model.bool_field = True
        self.assertEqual(test_model.whats_changed(), {'name', 'options'})

    def test_whats_changed_populates_properly_for_virtual_field(self):
        test_model = self.test_model
        self.assertEqual(test_model.whats_changed(include_virtual=True), set())
        test_model.bool_field = True
        self.assertEqual(test_model.whats_changed(include_virtual=True), {'options', 'bool_field'})
        test_model.bool_field = False
        self.assertEqual(test_model.whats_changed(include_virtual=True), set())

    def test_if_changes_are_identified(self):
        test_model = self.test_model
        self.assertFalse(test_model.has_changes())
        self.assertFalse(test_model.has_changed('name'))
        test_model.name = 'new_name'
        self.assertTrue(test_model.has_changes())
        self.assertTrue(test_model.has_changed('name'))
        test_model.name = 'my_name'
        self.assertFalse(test_model.has_changed('name'))
        self.assertFalse(test_model.has_changes())

    def test_if_old_value_returns_proper_value(self):
        test_model = self.test_model
        self.assertEqual(test_model.old_value('name'), 'my_name')
        test_model.name = 'new_name'
        self.assertEqual(test_model.old_value('name'), 'my_name')
        test_model.save()
        self.assertEqual(test_model.old_value('name'), 'new_name')

    def test_if_changes_are_empty_on_new_object(self):
        test_model = VirtualFieldsTestModel()
        self.assertEqual(test_model.whats_changed(), set())
        self.assertFalse(test_model.has_changed('name'))
        self.assertFalse(test_model.has_changes())
        test_model.name = 'new_name'
        self.assertEqual(test_model.whats_changed(), set())
        self.assertFalse(test_model.has_changed('name'))
        self.assertFalse(test_model.has_changes())


class TestForeignKeyTrackChangesModel(TestCase):
    def setUp(self):
        self.test_model = G(ForeignKeyTestModel, name='my_name')
        self.test_model_ref = G(ForeignKeyTestModel, name='my_name2', reference=self.test_model)

    def test_foreign_key_shows_proper_value(self):
        test_model = self.test_model_ref
        test_model.reference = None
        self.assertEqual(test_model.whats_changed(), {'reference'})
        self.assertEqual(test_model.old_value('reference'), self.test_model.id)


class TestDefinedFieldsTrackChangesModel(TestCase):
    def setUp(self):
        self.test_model = G(DefinedFieldsTestModel, name='my_name', other_name='other_name')

    def test_whats_changed_ignores_untracked_fields(self):
        test_model = self.test_model
        test_model.name = 'new_name'
        test_model.other_name = 'new_name'
        self.assertEqual(test_model.whats_changed(), {'name'})

    def test_untracked_field_raises_error(self):
        test_model = self.test_model
        test_model.name = 'new_name'
        test_model.other_name = 'new_name'
        self.assertRaises(KeyError, test_model.has_changed, 'other_name')
        self.assertRaises(KeyError, test_model.old_value, 'other_name')


class TestIgnoredFieldsTrackChangesModel(TestCase):
    def setUp(self):
        self.test_model = G(IgnoredFieldsTestModel, name='my_name', other_name='other_name')

    def test_whats_changed_ignores_ignored_fields(self):
        test_model = self.test_model
        test_model.name = 'new_name'
        test_model.other_name = 'new_name'
        self.assertEqual(test_model.whats_changed(), {'other_name'})

    def test_untracked_field_raises_error(self):
        test_model = self.test_model
        test_model.name = 'new_name'
        test_model.other_name = 'new_name'
        self.assertRaises(KeyError, test_model.has_changed, 'name')
        self.assertRaises(KeyError, test_model.old_value, 'name')
