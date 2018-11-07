# coding=UTF8
import copy

from django.contrib.postgres import fields as pg_fields
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, models, router, transaction
from django.db.models.signals import class_prepared
from django.dispatch import receiver
from jsonfield import JSONField
from retrying import retry

from apps.core import signals
from apps.core.fields import DictionaryField, LiveField, LowercaseCharField, NullableJSONField
from apps.core.helpers import Cached, generate_key
from apps.core.managers import LiveManager
from apps.core.permissions import Permission
from apps.core.querysets import AclQuerySet


class LiveAbstractModel(models.Model):
    """
    Inherit this class to enable delayed deletion for your model.

    If you define any unique fields, define them in combination with _is_live field, e.g.

    ```
    class Meta:
        unique_together = ('name', '_is_live')
    ```

    Otherwise _is_live will be added with db_index=True.

    NOTE:
    Mind that .delete() called on manager or queryset will be treated as a hard delete.
    Also, using soft_delete on a filtered set of objects will not run automatic background
    cleanup for them and needs to be handled manually.

    That's so because .soft_delete() doesn't fetch the actual objects like hard delete does,
    it runs an update which doesn't send any signals in Django.
    """
    objects = LiveManager()
    all_objects = LiveManager(include_soft_deleted=True)

    class Meta:
        abstract = True

    @property
    def is_live(self):
        return self._is_live

    def delete(self, using=None):
        self.soft_delete(using)

    def hard_delete(self, using=None):
        super().delete(using)

    def soft_delete(self, using=None):
        self._is_live = False
        signals.pre_soft_delete.send(sender=self.__class__, instance=self, using=using)
        self.save(using=using, update_fields=('_is_live',))
        signals.post_soft_delete.send(sender=self.__class__, instance=self, using=using)

    @staticmethod
    @receiver(class_prepared, dispatch_uid='LiveAbstractModel.add_is_live_field')
    def add_is_live_field(sender, **kwargs):
        if issubclass(sender, LiveAbstractModel) and not sender._meta.proxy:
            db_index = True
            for uniques in sender._meta.unique_together:
                if '_is_live' in uniques:
                    db_index = False

            field = LiveField(db_index=db_index)
            field.contribute_to_class(sender, '_is_live')

    def validate_unique(self, exclude=None):
        if exclude and '_is_live' in exclude:
            exclude.remove('_is_live')

        try:
            super().validate_unique(exclude=exclude)
        except ValidationError as ex:
            if NON_FIELD_ERRORS in ex.error_dict:
                error_dict = ex.error_dict
                errors = error_dict[NON_FIELD_ERRORS]

                new_errors = []
                for error in errors:
                    unique_check = error.params['unique_check']
                    if len(unique_check) == 1:
                        error_dict.setdefault(unique_check[0], []).append(error)
                    else:
                        new_errors.append(error)

                if new_errors:
                    error_dict[NON_FIELD_ERRORS] = new_errors
                else:
                    del error_dict[NON_FIELD_ERRORS]

            raise ex

    def unique_error_message(self, model_class, unique_check):
        if '_is_live' in unique_check and len(unique_check) == 2:
            unique_check = list(unique_check)
            unique_check.remove('_is_live')

        return super().unique_error_message(model_class=model_class, unique_check=unique_check)


class UniqueKeyAbstractModel(models.Model):
    KEY_FIELD_NAME = 'key'
    KEY_FIELD_KWARGS = {'unique': True}

    class Meta:
        abstract = True

    @retry(retry_on_exception=lambda x: isinstance(x, IntegrityError), stop_max_attempt_number=3)
    def _retry_save(self, using=None, *args, **kwargs):
        using = using or router.db_for_write(self.__class__, instance=self)

        with transaction.atomic(using=using):
            setattr(self, self.KEY_FIELD_NAME, self.generate_key())
            super().save(using=using, *args, **kwargs)

    def save(self, reset=False, force_insert=False, *args, **kwargs):
        if self.pk and getattr(self, self.KEY_FIELD_NAME):
            if not reset:
                super().save(force_insert=force_insert, *args, **kwargs)
                return
            else:
                force_insert = False

        self._retry_save(force_insert=force_insert, *args, **kwargs)

    @staticmethod
    @receiver(class_prepared, dispatch_uid='UniqueKeyAbstractModel.add_key_field')
    def add_key_field(sender, **kwargs):
        if issubclass(sender, UniqueKeyAbstractModel) and not sender._meta.proxy:
            field = LowercaseCharField(max_length=40, **sender.KEY_FIELD_KWARGS)
            field.contribute_to_class(sender, sender.KEY_FIELD_NAME)

    def generate_key(self):
        return generate_key()

    def reset(self):
        self.save(reset=True)


class TrackChangesAbstractModel(models.Model):
    """
    Tracks property changes on a model instance.

    The changed list of properties is refreshed on model initialization
    and save.
    """

    TRACKED_FIELDS = None
    IGNORED_FIELDS = None

    _track_data = None

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.store()

    @staticmethod
    @receiver(class_prepared, dispatch_uid='TrackChangesAbstractModel.prepare_class_tracked_fields')
    def prepare_class_tracked_fields(sender, **kwargs):
        if issubclass(sender, TrackChangesAbstractModel):
            sender.process_tracked_fields()

    def save(self, *args, **kwargs):
        # If we're doing standard save, we cover all fields and we're either not creating or do not have changes
        #  - then no insert/update necessary
        if not kwargs and not args and self.IGNORED_FIELDS is None and self.TRACKED_FIELDS is None \
                and getattr(self, 'id', None) is not None and not self.has_changes():
            return

        super().save(*args, **kwargs)
        self.store()

    @classmethod
    def process_tracked_fields(cls):
        fields = cls.TRACKED_FIELDS
        ignored_fields = cls.IGNORED_FIELDS
        meta = cls._meta
        fields_map = dict()

        if fields:
            for field_name in fields:
                fields_map[field_name] = meta.get_field(field_name)
        else:
            fields_map = {field.name: field for field in meta.fields}

        # Ignore pk field at all times
        pk_field = meta.pk.name
        if pk_field in fields_map:
            del fields_map[pk_field]

        if ignored_fields:
            for field_name in ignored_fields:
                # Make sure field exists
                meta.get_field(field_name)
                if field_name in fields_map:
                    del fields_map[field_name]

        cls._fields_map = fields_map

    def store(self):
        """Updates a local copy of attributes values"""

        track_data = dict()

        deferred_fields = self.get_deferred_fields()
        if self.pk:
            for field_name, field in self._fields_map.items():
                if field.attname in deferred_fields:
                    continue
                value = self._get_field_value(field)

                if isinstance(value, dict):
                    value = copy.deepcopy(value)

                track_data[field_name] = value

        self._track_data = track_data

    def has_changed(self, field):
        """Returns ``True`` if ``field`` has changed since initialization."""

        if not self._track_data:
            return False
        return self._track_data[field] != self._get_field_value(self._fields_map[field])

    def has_changes(self):
        if not self._track_data:
            return False
        return bool(self.whats_changed(check=True))

    def old_value(self, field):
        """Returns the previous value of ``field``"""

        return self._track_data[field]

    def whats_changed(self, check=False, include_virtual=False, skip_fields=None):
        """Returns a list of changed attributes."""
        changed = set()
        if not self._track_data:
            return changed

        fields = self._fields_map

        for field_name, value in self._track_data.items():
            field = fields[field_name]

            if skip_fields and field_name in skip_fields:
                continue
            if field.column is None and not include_virtual:
                continue

            new_value = self._get_field_value(field)
            if value != new_value:
                if check:
                    return True
                changed.add(field_name)
        return changed

    def _get_field_value(self, field):
        if isinstance(field, models.ForeignKey):
            return getattr(self, field.get_attname(), None)
        elif isinstance(field, DictionaryField):
            if field.schema_mode:
                hstore_fields = getattr(self, '_hstore_virtual_fields', {})
                return {hstore_field.name: getattr(self, hstore_field.name) for hstore_field in hstore_fields.values()}
            return field.get_prep_value(getattr(self, field.name, None))
        elif isinstance(field, models.FileField) and hasattr(self, field.name):
            return field.attr_class(self, field, getattr(self, field.name).name)
        return getattr(self, field.name, None)


class CacheableAbstractModel(models.Model):
    """
    Inherit from this model to make it possible to use with Cached() helper.
    This takes care of invalidation and cache updates.

    Example usage:

    ```
    instance = Cached(Instance, kwargs=dict(pk=1))
    ```

    NOTE:
    Mind that batch .soft_delete() or .update() when inheriting from both CacheableAbstractModel and LiveAbstractModel
    will not update or invalidate the cache as it does not send post_save.
    Using with objects that have different primary_key defined, can bring unexpected results.
    """

    SYNC_INVALIDATION = False

    class Meta:
        abstract = True

    def invalidate_cache(self):
        Cached(self.__class__).invalidate(self)


class MetadataAbstractModel(models.Model):
    metadata = JSONField(default={}, blank=True)

    class Meta:
        abstract = True


class DescriptionAbstractModel(models.Model):
    description = models.TextField(blank=True, max_length=256)

    class Meta:
        abstract = True


class LabelAbstractModel(models.Model):
    label = models.CharField(blank=True, max_length=64)

    class Meta:
        abstract = True


class LabelDescriptionAbstractModel(LabelAbstractModel, DescriptionAbstractModel):
    class Meta:
        abstract = True


class CreatedUpdatedAtAbstractModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AclAbstractBaseModel(models.Model):
    DEFAULT_ACL = {}

    READ_PERMISSION = Permission('read', actions=('retrieve',))
    WRITE_PERMISSION = Permission('write', actions=('update', 'partial_update', 'destroy'))

    OBJECT_ACL_PERMISSIONS = (
        READ_PERMISSION,
        WRITE_PERMISSION,
    )

    GET_PERMISSION = Permission('get', actions=('retrieve',))
    LIST_PERMISSION = Permission('list', actions=('list',))
    CREATE_PERMISSION = Permission('create', actions=('create',))
    UPDATE_PERMISSION = Permission('update', actions=('update', 'partial_update',))
    DELETE_PERMISSION = Permission('delete', actions=('destroy',))

    ENDPOINT_ACL_PERMISSIONS = (
        GET_PERMISSION,
        LIST_PERMISSION,
        CREATE_PERMISSION,
        UPDATE_PERMISSION,
        DELETE_PERMISSION,
    )

    class Meta:
        abstract = True

    @classmethod
    def get_acl_permissions(cls):
        return cls.OBJECT_ACL_PERMISSIONS

    @classmethod
    def get_acl_permission_values(cls):
        return [perm.key for perm in cls.get_acl_permissions()]

    @classmethod
    def get_endpoint_acl_permissions(cls):
        return cls.ENDPOINT_ACL_PERMISSIONS

    @classmethod
    def get_endpoint_acl_permission_values(cls):
        return [perm.key for perm in cls.get_endpoint_acl_permissions()]


class SimpleAclAbstractModel(AclAbstractBaseModel):
    acl = NullableJSONField()

    class Meta:
        abstract = True

    @staticmethod
    @receiver(class_prepared, dispatch_uid='SimpleAclAbstractModel.prepare_acl_field')
    def prepare_acl_field(sender, **kwargs):
        if issubclass(sender, SimpleAclAbstractModel):
            # Set default ACL from model
            sender._meta.get_field('acl').default = sender.DEFAULT_ACL


class AclAbstractModel(SimpleAclAbstractModel):
    _users = pg_fields.ArrayField(models.IntegerField(), default=list, blank=True)
    _groups = pg_fields.ArrayField(models.IntegerField(), default=list, blank=True)
    _public = models.BooleanField(default=False)

    class Meta:
        abstract = True

    @staticmethod
    @receiver(class_prepared, dispatch_uid='AclAbstractModel.prepare_acl_manager')
    def prepare_acl_manager(sender, **kwargs):
        if issubclass(sender, AclAbstractModel):
            manager = sender.objects
            orig_queryset_class = manager._queryset_class
            if issubclass(orig_queryset_class, AclQuerySet):
                parent = (orig_queryset_class,)
            else:
                parent = (AclQuerySet, orig_queryset_class)

            # Django abstract manager inheritance is pretty much non-existing so we just create it for each model
            queryset_class = type('AclQuery', parent, {})
            new_manager = sender.objects.from_queryset(queryset_class)()
            new_manager.name = manager.name
            new_manager.model = sender

            sender.objects = new_manager
