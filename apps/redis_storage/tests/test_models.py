from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase
from django.utils import timezone
from django_dynamic_fixture import G

from apps.core.helpers import redis
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.contextmanagers import instance_context
from apps.instances.models import Instance
from apps.redis_storage.models import RedisModel

from .. import fields as redis_fields


class MyModel(RedisModel):
    char = redis_fields.CharField(default='abc')
    date = redis_fields.DatetimeField()
    int = redis_fields.IntegerField()
    json = redis_fields.JSONField(default={})
    bool = redis_fields.BooleanField(default=True)

    ttl = 120
    trimmed_ttl = 30
    list_max_size = 20


class MyModelWithListArgs(RedisModel):
    char = redis_fields.CharField(default='abc')
    list_template_args = '{arg1}'


class MyModelWithObjectArgs(RedisModel):
    char = redis_fields.CharField(default='abc')
    object_template_args = '{arg1}'


class TenantModel(RedisModel):
    tenant_model = True
    char = redis_fields.CharField(default='abc')


class TestModels(CleanupTestCaseMixin, TestCase):
    def assert_equal_object_data(self, obj, object_data):
        for key, val in object_data.items():
            self.assertEqual(getattr(obj, key), val)

    def test_creating(self):
        now = timezone.now()
        obj1 = MyModel.create(int=13, json=[], bool=False)
        obj2 = MyModel.create(char='cba', date=now)
        model_list = MyModel.list()
        self.assertEqual(len(model_list), 2)

        obj1_data = {'char': 'abc', 'date': None, 'int': 13, 'json': [], 'bool': False}
        obj2_data = {'char': 'cba', 'date': now, 'int': None, 'json': {}, 'bool': True}

        self.assert_equal_object_data(obj1, obj1_data)
        self.assert_equal_object_data(obj2, obj2_data)
        self.assert_equal_object_data(model_list[1], obj1_data)
        self.assert_equal_object_data(model_list[0], obj2_data)

        obj3 = MyModelWithListArgs.create(arg1='val')
        self.assertEqual(len(MyModelWithListArgs.list(arg1='val')), 1)
        self.assert_equal_object_data(obj3, {'char': 'abc'})

    def test_getting(self):
        obj = MyModel.create(int=13, json=[], bool=False)
        obj = MyModel.get(pk=obj.pk)
        obj_data = {'char': 'abc', 'date': None, 'int': 13, 'json': [], 'bool': False}
        self.assert_equal_object_data(obj, obj_data)

        # Check if 404 is handled properly
        self.assertRaises(ObjectDoesNotExist, MyModel.get, pk='abc')

    def test_updating(self):
        obj = MyModel.create(char='cba')
        model_list = MyModel.list()
        self.assertEqual(len(model_list), 1)
        self.assert_equal_object_data(model_list[0], {'char': 'cba', 'date': None})

        # Assert that ttl is set
        self.assertLessEqual(redis.ttl(MyModel.get_list_key()), MyModel.ttl)
        self.assertLessEqual(redis.ttl(MyModel.get_object_key(pk=obj.pk)), MyModel.ttl)

        now = timezone.now()
        updated = MyModel.update(obj.pk, updated={'char': None, 'date': now})
        self.assertTrue(updated)
        model_list = MyModel.list()
        self.assertEqual(len(model_list), 1)
        self.assert_equal_object_data(model_list[0], {'pk': obj.pk, 'char': None, 'date': now})

        # Assert that ttl is set
        self.assertLessEqual(redis.ttl(MyModel.get_list_key()), MyModel.ttl)
        self.assertLessEqual(redis.ttl(MyModel.get_object_key(pk=obj.pk)), MyModel.ttl)

    def test_updating_with_expected(self):
        obj = MyModel.create(char='cba')

        # Check with correct expected value
        updated = MyModel.update(obj.pk, updated={'char': None, 'int': 15}, expected={'char': 'cba'})
        self.assertTrue(updated)
        model_list = MyModel.list()
        self.assertEqual(len(model_list), 1)
        self.assert_equal_object_data(model_list[0], {'pk': obj.pk, 'char': None, 'int': 15})

        # Check with incorrect expected value
        updated = MyModel.update(obj.pk, updated={'char': 'cba', 'int': 23}, expected={'char': 'cba'})
        self.assertFalse(updated)
        model_list = MyModel.list()
        self.assertEqual(len(model_list), 1)
        self.assert_equal_object_data(model_list[0], {'pk': obj.pk, 'char': None, 'int': 15})

    def test_updating_model_with_listargs(self):
        obj = MyModelWithListArgs.create(arg1='val')
        model_list = MyModelWithListArgs.list(arg1='val')
        self.assertEqual(len(model_list), 1)
        self.assert_equal_object_data(model_list[0], {'char': 'abc'})

        # Assert that ttl is set
        self.assertEqual(redis.ttl(MyModelWithListArgs.get_list_key(arg1='val')), -1)
        self.assertEqual(redis.ttl(MyModelWithListArgs.get_object_key(pk=obj.pk)), -1)

        MyModelWithListArgs.update(obj.pk, updated={'char': 'abcd'})
        model_list = MyModelWithListArgs.list(arg1='val')
        self.assertEqual(len(model_list), 1)
        self.assert_equal_object_data(model_list[0], {'pk': obj.pk, 'char': 'abcd'})

        # Assert that ttl is set
        self.assertEqual(redis.ttl(MyModelWithListArgs.get_list_key(arg1='val')), -1)
        self.assertEqual(redis.ttl(MyModelWithListArgs.get_object_key(pk=obj.pk)), -1)

    def test_deleting(self):
        obj = MyModel.create(char='cba')
        model_list = MyModel.list()
        self.assertEqual(len(model_list), 1)

        obj.delete()
        model_list = MyModel.list()
        self.assertEqual(len(model_list), 0)
        self.assertRaises(ObjectDoesNotExist, MyModel.get, obj.pk)

    def test_list_handling_expired_objects(self):
        obj = MyModel.create(char='cba')
        model_list = MyModel.list()
        self.assertEqual(len(model_list), 1)

        redis.delete(obj.get_object_key(pk=obj.pk))

        self.assertRaises(ObjectDoesNotExist, MyModel.get, obj.pk)
        list_key = MyModel.get_list_key()
        self.assertEqual(redis.zcard(list_key), 1)
        model_list = MyModel.list()
        self.assertEqual(len(model_list), 0)

    def test_args_separation(self):
        MyModelWithListArgs.create(arg1='val')
        MyModelWithListArgs.create(arg1='val2')
        MyModelWithListArgs.create(arg1='val2')

        model_list = MyModelWithListArgs.list(arg1='val')
        self.assertEqual(len(model_list), 1)
        model_list = MyModelWithListArgs.list(arg1='val2')
        self.assertEqual(len(model_list), 2)

        MyModelWithObjectArgs.create(arg1='val')
        MyModelWithObjectArgs.create(arg1='val2')
        MyModelWithObjectArgs.create(arg1='val2')

        model_list = MyModelWithObjectArgs.list()
        self.assertEqual(len(model_list), 3)
        redis_keys = redis.zrange(MyModelWithObjectArgs.get_list_key(), 0, 100)
        self.assertEqual(len([key for key in redis_keys if key.decode().endswith('val')]), 1)
        self.assertEqual(len([key for key in redis_keys if key.decode().endswith('val2')]), 2)

    def test_trimming_after_create(self):
        obj = MyModel.create(int=1)
        for i in range(25):
            MyModel.create(int=i)
        key = obj.get_object_key(pk=obj.pk)
        self.assertLessEqual(redis.ttl(key), MyModel.trimmed_ttl)

    def test_listing(self):
        for i in range(25):
            MyModel.create(int=i)

        model_list = MyModel.list()
        self.assertEqual(len(model_list), MyModel.list_max_size)

        model_list = MyModel.list(limit=10)
        self.assertEqual(len(model_list), 10)
        # Check if newest element is on first place
        self.assertEqual(model_list[0].int, 24)

        model_list = MyModel.list(limit=10, ordering='asc')
        self.assertEqual(len(model_list), 10)
        # Check if oldest non-trimmed element is on first place
        self.assertEqual(model_list[0].int, 5)

    def test_listing_with_deferred_field(self):
        for i in range(10):
            MyModel.create(int=i)

        model_list = MyModel.list(deferred_fields={'int'})
        self.assertTrue(all(model.int is None for model in model_list))

    def test_listing_with_filter(self):
        for i in range(10):
            MyModel.create(int=i)

        model_list = MyModel.list(min_pk=3)
        self.assertEqual(len(model_list), 8)

        model_list = MyModel.list(max_pk=3)
        self.assertEqual(len(model_list), 3)

        model_list = MyModel.list(min_pk=3, max_pk=4)
        self.assertEqual(len(model_list), 2)

    def test_creating_without_required_arg(self):
        self.assertRaises(KeyError, MyModelWithListArgs.create, char='cba')

    def test_listing_without_required_arg(self):
        self.assertRaises(KeyError, MyModelWithListArgs.list, char='cba')

    def test_saving_fresh_object_with_updated_fields(self):
        self.assertRaises(RuntimeError, MyModel().save, update_fields=('char',))

    def test_tenant_model_separation(self):
        self.assertRaises(AttributeError, TenantModel().save)
        inst1 = G(Instance, name='test')
        inst2 = G(Instance, name='test2')
        expected_pk = 1

        with instance_context(inst1):
            model1 = TenantModel.create(char='A')
        with instance_context(inst2):
            model2 = TenantModel.create(char='B')

        self.assertEqual(model1.pk, model2.pk)

        # Now refresh from redis just to be sure we are not dealing with bogus data
        with instance_context(inst1):
            model1 = TenantModel.get(pk=expected_pk)
            object_key1 = model1.get_object_key(pk=expected_pk)
        with instance_context(inst2):
            model2 = TenantModel.get(pk=model2.pk)
            object_key2 = model2.get_object_key(pk=expected_pk)

        self.assertNotEqual(model1.char, model2.char)
        self.assertNotEqual(object_key1, object_key2)

    def test_incorrect_json(self):
        model1 = MyModel.create(json='\ud977\ufffd')
        model1 = MyModel.get(pk=model1.pk)
        self.assertEqual(model1.json, {})
