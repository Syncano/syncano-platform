# coding=UTF8
from collections import defaultdict

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import models
from django.utils.encoding import force_bytes
from jsonfield import JSONField
from rest_framework.validators import UniqueValidator

from apps.core.abstract_models import (
    AclAbstractModel,
    CacheableAbstractModel,
    DescriptionAbstractModel,
    LiveAbstractModel,
    MetadataAbstractModel,
    TrackChangesAbstractModel
)
from apps.core.fields import DictionaryField, NullableJSONField, StrippedSlugField
from apps.core.helpers import Cached, MetaIntEnum, get_schema_cache
from apps.core.managers import LiveManager
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS
from apps.core.querysets import CountEstimateLiveQuerySet
from apps.core.validators import NotInValidator
from apps.data.helpers import FIELD_CLASS_MAP, convert_field_type_to_db_type
from apps.data.querysets import KlassQuerySet

from .validators import SchemaValidator

DISALLOWED_KLASS_NAMES = {'self', 'user', 'users', 'acl'}
KLASS_SCHEMA_CACHE_TEMPLATE = 'klass:{pk}:schema:'


class Klass(AclAbstractModel, DescriptionAbstractModel, MetadataAbstractModel, CacheableAbstractModel,
            TrackChangesAbstractModel, LiveAbstractModel):
    """Represents a schema of the DataObject"""
    DEFAULT_ACL = {'*': ['read']}
    DEFAULT_ENDPOINT_ACL = {'*': ['get', 'list', 'create', 'update', 'delete']}

    PERMISSION_CONFIG = {
        'api_key': {API_PERMISSIONS.READ},
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }
    USER_PROFILE_NAME = 'user_profile'

    class PERMISSIONS(MetaIntEnum):
        NONE = 0, 'none'
        READ = 1, 'read'
        CREATE_OBJECTS = 2, 'create_objects'

    name = StrippedSlugField(max_length=64,
                             validators=[NotInValidator(values=DISALLOWED_KLASS_NAMES)],
                             allow_hyphen=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revision = models.IntegerField(default=1)

    schema = JSONField(default=[])
    mapping = DictionaryField()
    existing_indexes = JSONField(default={})
    index_changes = JSONField(null=True)
    refs = JSONField(default={})

    # v1 permission fields
    group = models.ForeignKey('users.Group', null=True, blank=True, on_delete=models.SET_NULL)
    group_permissions = models.SmallIntegerField(default=PERMISSIONS.CREATE_OBJECTS, choices=PERMISSIONS.as_choices(),
                                                 db_index=True)
    other_permissions = models.SmallIntegerField(default=PERMISSIONS.CREATE_OBJECTS, choices=PERMISSIONS.as_choices(),
                                                 db_index=True)

    # v2 permission fields
    objects_acl = NullableJSONField(default=DEFAULT_ENDPOINT_ACL)
    visible = models.BooleanField(default=True, db_index=True)

    objects = LiveManager.from_queryset(KlassQuerySet)()

    class Meta:
        verbose_name = 'Class'
        verbose_name_plural = 'Classes'
        ordering = ('id',)
        unique_together = ('name', '_is_live')

    def __str__(self):
        return 'Klass[id=%s, name=%s]' % (
            self.pk,
            self.name,
        )

    def save(self, *args, **kwargs):
        new = self.id is None
        schema_has_changed = self.has_changed('schema')

        # Check if migration is needed
        if schema_has_changed:
            self.revision += 1
            old_schema = self.old_value('schema')
        else:
            old_schema = None

        if new or schema_has_changed:
            old_mapping = self.mapping.copy()
            self.mapping = self.process_mapping(old_schema)
            index_changes, new_indexes = Klass.process_index_changes(self.existing_indexes,
                                                                     old_schema, self.schema,
                                                                     old_mapping, self.mapping)

            if index_changes:
                self.index_changes = index_changes
                self.existing_indexes = new_indexes

        super().save(*args, **kwargs)

        # Process cache count
        if new:
            self._objects_count = 0

    @property
    def objects_count(self):
        if not hasattr(self, '_objects_count'):
            self._objects_count = self.data_objects.count_estimate()
        return self._objects_count

    @property
    def is_locked(self):
        return self.index_changes is not None

    @property
    def is_user_profile(self):
        return self.name == Klass.USER_PROFILE_NAME and self.id is not None

    @property
    def migration_status(self):
        if self.is_locked:
            return 'migrating'
        else:
            return 'ready'

    def unlock(self, index_changes=None, rollback=False):
        if index_changes:
            for index_type, new_indexes in index_changes.items():
                self.existing_indexes[index_type] = self.existing_indexes.get(index_type, []) + new_indexes
        self.index_changes = None
        if rollback:
            self.cleanup_schema()
        self.save(update_fields=['existing_indexes', 'index_changes', 'schema'])

    def cleanup_schema(self):
        index_types = {'order': (SchemaValidator.order_index_key,), 'filter': (SchemaValidator.filter_index_key,
                                                                               SchemaValidator.unique_index_key)}

        for index_type, index_keys in index_types.items():
            existing_indexes = self.existing_indexes.get(index_type, [])

            for field_definition in self.schema:
                field_mapping = self.mapping[field_definition['name']]

                if field_definition.get(index_keys[0], False) and field_mapping not in existing_indexes:
                    for key in index_keys:
                        if key in field_definition:
                            del field_definition[key]

    @classmethod
    def cleanup_refs_props(cls, klass, klass_schema):
        # Clean ref props
        for f_name, ref_props in klass.refs.get('props', {}).items():
            for prop, prop_sockets in list(ref_props.items()):
                if not prop_sockets:
                    if prop in klass_schema[f_name]:
                        del klass_schema[f_name][prop]
                    del ref_props[prop]
                else:
                    klass_schema[f_name][prop] = True
        for f_name, ref_props in list(klass.refs.get('props', {}).items()):
            if not ref_props:
                del klass.refs['props'][f_name]

    def cleanup_refs(self, save=False):
        # Process fields.
        fields_to_del = []
        klass_schema = {f['name']: f for f in self.schema}

        Klass.cleanup_refs_props(self, klass_schema)

        # Prepare fields to delete
        for f_name, f_sockets in list(self.refs.get('fields', {}).items()):
            if f_sockets:
                continue
            if f_name in klass_schema:
                fields_to_del.append(f_name)
                del klass_schema[f_name]
            del self.refs['fields'][f_name]

        self.schema = list(klass_schema.values())

        if save:
            self.save()

    def process_mapping(self, old_schema):
        old_mapping = self.mapping or {}
        old_schema = old_schema or []
        new_schema = self.schema

        mapping = dict()

        old_field_def_dict = {field['name']: field for field in old_schema}

        for field_definition in new_schema:
            field_name = field_definition['name']
            field_source = None

            if field_name in old_mapping:
                old_field_definition = old_field_def_dict[field_name]

                old_field_setup = {key: old_field_definition[key] for key in
                                   set(old_field_definition.keys()) - SchemaValidator.possible_indexed_keys}
                field_setup = {key: field_definition[key] for key in
                               set(field_definition.keys()) - SchemaValidator.possible_indexed_keys}

                if field_definition['type'] == old_field_definition['type'] \
                        and old_field_setup == field_setup:
                    field_source = old_mapping[field_name]

            if field_source is None:
                field_source = '%d_%s' % (self.revision, field_name)

            mapping[field_name] = field_source
        return mapping

    @classmethod
    def process_index_changes(cls, old_indexes, old_schema, new_schema, old_mapping, new_mapping):
        # Prepare index changes
        old_schema = old_schema or []

        index_types = {'order': SchemaValidator.order_index_key, 'filter': SchemaValidator.filter_index_key}

        index_changes = defaultdict(lambda: defaultdict(list))
        new_indexes = defaultdict(list)
        indexed_fields = defaultdict(set)

        # Process new schema to look for indexes to add
        for field_definition in new_schema:
            for index_key, index_type_field in index_types.items():
                field_type = field_definition['type']
                field_source = new_mapping[field_definition['name']]

                if field_definition.get(index_type_field, False):
                    # Check if same index was already defined
                    index_was_there = index_key in old_indexes and field_source in old_indexes[index_key]
                    indexed_fields[index_key].add(field_source)

                    if not index_was_there:
                        field_db_type = convert_field_type_to_db_type(field_source=field_source,
                                                                      field_type=field_definition['type'])
                        index_flags = {}
                        if field_definition.get(SchemaValidator.unique_index_key, False):
                            index_flags['unique'] = True
                        index_changes[index_key]['+'].append((field_source, field_db_type, field_type, index_flags))
                    else:
                        new_indexes[index_key].append(field_source)

        # Process old schema to look for indexes to remove
        for field_definition in old_schema:
            for index_key, index_type_field in index_types.items():
                field_name = field_definition['name']
                field_type = field_definition['type']
                field_source = old_mapping[field_name]

                # If index was defined but no longer is, remove it
                if field_definition.get(index_type_field, False) and field_source not in indexed_fields[index_key]:
                    index_changes[index_key]['-'].append((field_source, field_type))

        return dict(index_changes), dict(new_indexes)

    def clean(self):
        # Cannot modify locked class
        if self.is_locked:
            raise ValidationError('Cannot modify class. Please wait until migration process has finished.')

    def convert_schema_to_django_schema(self):
        django_schema = []
        schema = self.schema
        mapping = self.mapping
        indexes = self.existing_indexes or {}

        for field_def in schema:
            source = mapping[field_def['name']]
            # Skip fields that should be unique, but are not indexed yet.
            unique = field_def.get('unique', False)
            if unique and source not in indexes.get('filter', {}):
                continue

            field_cls, params = FIELD_CLASS_MAP[field_def['type']]
            params = params.copy()

            params['filter_index'] = source in indexes.get('filter', {})
            params['order_index'] = source in indexes.get('order', {})
            if unique:
                params['validators'] = [UniqueValidator(queryset=DataObject.objects.filter(_klass=self.pk))]

            for key in set(field_def.keys()) - SchemaValidator.possible_indexed_keys:
                params[key] = field_def[key]

            django_schema.append({
                'name': field_def['name'],
                'class': field_cls,
                'source': source,
                'kwargs': params
            })
        return django_schema

    @classmethod
    def get_user_profile(cls):
        return Cached(cls, kwargs=dict(name=cls.USER_PROFILE_NAME)).get()


class DataObject(AclAbstractModel, TrackChangesAbstractModel, LiveAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    class PERMISSIONS(MetaIntEnum):
        NONE = 0, 'none'
        READ = 1, 'read'
        WRITE = 2, 'write'
        FULL = 3, 'full'

    _klass = models.ForeignKey(Klass, related_name='data_objects', on_delete=models.CASCADE)
    _data = DictionaryField()
    _files = DictionaryField()

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    revision = models.IntegerField(default=1, db_index=True)

    # v1 permission fields
    owner = models.ForeignKey('users.User', null=True, blank=True, default=None, on_delete=models.CASCADE)
    owner_permissions = models.SmallIntegerField(default=PERMISSIONS.FULL, choices=PERMISSIONS.as_choices(),
                                                 db_index=True)
    group = models.ForeignKey('users.Group', null=True, blank=True, default=None, on_delete=models.SET_NULL)
    group_permissions = models.SmallIntegerField(default=PERMISSIONS.NONE, choices=PERMISSIONS.as_choices(),
                                                 db_index=True)
    other_permissions = models.SmallIntegerField(default=PERMISSIONS.NONE, choices=PERMISSIONS.as_choices(),
                                                 db_index=True)

    channel = models.ForeignKey('channels.Channel', null=True, blank=True, default=None, on_delete=models.CASCADE)
    channel_room = models.CharField(max_length=64, null=True, blank=True, default=None, db_index=True)

    objects = LiveManager.from_queryset(CountEstimateLiveQuerySet)()

    class Meta:
        ordering = ('id',)
        verbose_name = 'DataObject'

    def __str__(self):
        return 'DataObject[id=%s, klass_name=%s]' % (
            self.pk,
            self._klass.name,
        )

    def clean(self):
        # 8 is average serialization overhead length per field: >"":"",<
        data = self._data
        object_size = 6 * len(data)
        # Minimum overhead is 103 which is the length of most basic object structure:
        # {"id":2147483647,"created_at":"0000-00-00T00:00:00.000000Z","updated_at":"0000-00-00T00:00:00.000000Z"}
        object_size += 103

        max_size = settings.DATA_OBJECT_SIZE_MAX

        for key, value in data.items():
            object_size += len(key)
            if value:
                if isinstance(value, File):
                    # Potentially longest filename:
                    # 2147483647/2147483647/7a584c438ae481a85e9079f8feab1e289a965fb9.verylongextensi
                    object_size += 78
                else:
                    object_size += len(force_bytes(value))

            if object_size > max_size:
                raise ValidationError('Object maximum size exceeded.')

    @classmethod
    def load_klass(cls, klass):
        cache = get_schema_cache()
        cache_key = KLASS_SCHEMA_CACHE_TEMPLATE.format(pk=klass.pk)

        schema_data = cache.get(cache_key)
        if schema_data is None:
            schema_data = klass.convert_schema_to_django_schema()
            cache[cache_key] = schema_data

        field = cls._meta.get_field('_data')
        field.reload_schema(schema_data)
        cls.process_tracked_fields()
        cls.loaded_klass = klass
