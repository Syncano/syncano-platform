# coding=UTF8

from django.db import models
from django.db.models.signals import post_save, pre_save
from rest_framework import serializers
from timezone_utils.fields import TimeZoneField

from apps.core.contextmanagers import ignore_signal
from apps.core.helpers import camel_to_under

from .fields import BinaryField

NOFILES = dict()


class ModelBackup:
    """
    ModelBackup is used for customizing backup and restore of objects.
    Current implementation uses queryset.values for fetching objects
    from DB, and bulk_create to restore them.
    You could provide your own serializer for fields by defining a class
    attribute with given name. eg

        class CustomBackup(ModelBackup):
            field_name = serializers.CustomSerializer

    It is expected to be rest_framework
    field/serializer instance. By default this class defines custom
    serializers for common field types like DateTimeField, DateField,
    TimeZoneField, UUIDField and BinaryFields.
    """
    BATCH_SIZE = 1000
    lookup_field = 'id'
    details_lookup_field = None  # lookup_field for details list. Use lookup_field if not specified.
    include_details = None

    DEFAULT_SERIALIZERS = {
        models.DateTimeField: serializers.DateTimeField,
        models.DateField: serializers.DateField,
        TimeZoneField: serializers.CharField,
        models.UUIDField: serializers.UUIDField,
        models.BinaryField: BinaryField
    }

    def __init__(self, model, site):
        self.model = model
        self.site = site
        self.auto_fields = []
        self.custom_serializers = {}
        for field in self.model._meta.local_fields:
            if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
                self.auto_fields.append(field)
            field_type = type(field)
            name = field.get_attname()
            custom = getattr(self, name, None)
            if not custom and field_type in self.DEFAULT_SERIALIZERS:
                custom = self.DEFAULT_SERIALIZERS[field_type]()
            if custom:
                self.custom_serializers[name] = custom

    def get_name(self):
        return camel_to_under(self.model._meta.verbose_name.replace(' ', ''))

    def get_dependencies(self):
        """ Get model dependencies in a form
        {field_name: related Model}
        """
        deps = {}
        for field in self.model._meta.local_fields:
            related_model = getattr(field, 'related_model', None)
            if related_model and related_model._meta.label in self.site._registry:
                deps[field.attname] = related_model
        return deps

    def get_queryset(self, query_args=None):
        queryset = self.model.objects.all()
        if query_args:
            kwargs = {}
            id_list = query_args.get(self.get_name(), None)
            if id_list is not None:
                if id_list:
                    kwargs['%s__in' % self.lookup_field] = id_list
                else:  # empty list
                    return queryset.none()
            for field_name, model in self.get_dependencies().items():
                try:
                    model_opts = self.site.get_options_for_model(model)
                    pk_name = model._meta.pk.name
                except KeyError:
                    # If site doesn't have registerd model for this dependency
                    # skip it
                    continue
                else:
                    if model_opts.get_name() in query_args:
                        kwargs[field_name + '__in'] = model_opts.get_queryset(query_args).values(pk_name)
            if kwargs:
                queryset = queryset.filter(**kwargs)
        return queryset

    def backup(self, storage, query_args=None):
        """
        This methods, adds objects/files to storage.
        Objects are addedd by storage.append.
        Files are added by storage.add_file.
        """
        # fetch current model migrations
        # save to storage
        queryset = self.get_queryset(query_args).values().order_by('id')
        last_pk = 0
        while True:
            fetched = 0
            query = queryset.filter(id__gt=last_pk)
            for fetched, obj in enumerate(query[:self.BATCH_SIZE].iterator(), 1):
                self.backup_object(storage, self.to_representation(obj))
                last_pk = obj['id']
            if fetched < self.BATCH_SIZE:
                break

    def backup_object(self, storage, obj):
        """Save representaion of object to storage."""
        storage.append(obj=obj, options=self)

    def to_representation(self, obj):
        """Method returning representation of object."""
        for name, serializer in self.custom_serializers.items():
            if obj[name] is not None:
                obj[name] = serializer.to_representation(obj[name])
        return obj

    def save_batch(self, object_list, partial=False):
        """
        Save a list of model instances.
        """
        if not partial:
            self.model.objects.bulk_create(object_list)

        else:
            for obj in object_list:
                # lookup conflicting object
                # if there is one, overwrite it with existing object.pk
                # if there is none, obj.pk will become None
                existing_pk = self.model.objects\
                    .values_list('pk', flat=True)\
                    .filter(**{self.lookup_field: getattr(obj, self.lookup_field)})\
                    .first()
                if existing_pk:
                    obj.pk = existing_pk
                self.update_object(obj)

    def update_object(self, obj):
        with ignore_signal(post_save, pre_save):
            obj.save()

    def restore(self, storage, partial=False):
        """
        Restore objects from storage.
        This method disables auto_now* fields before restore, and enables them
        after. Objects are collected in batches and saved using save_batch.
        Object representations are fetched from iterator returned by
        storage.get_model_storage. They are converted to instances in
        to_instance method
        Args:
            storage (Storage): storage to get objects from
        """
        batch = []

        # Disable auto_now* fields
        auto_now = set()

        for field in self.auto_fields:
            # these properties are exclusive so if a field is auto_now it's not
            # auto_now_add and vice versa
            if field.auto_now:
                field.auto_now = False
                auto_now.add(field)
            else:
                field.auto_now_add = False
        try:
            for value in storage.get_model_storage(self.get_name()):
                batch.append(self.to_instance(storage, value))
                if len(batch) > self.BATCH_SIZE:
                    self.save_batch(batch, partial)
                    batch = []

            if batch:
                self.save_batch(batch, partial)
        finally:
            # Enable auto_now* fields
            for field in self.auto_fields:
                # enable auto_now or auto_now_add
                if field in auto_now:
                    field.auto_now = True
                else:
                    field.auto_now_add = True

    def to_instance(self, storage, representation):
        """
        Return instance of model for given representation. Instance
        doesn't has to be saved to DB. It's later saved in save_batch method.
        files is a mapping of {original_file_path: backup_file_path}
        """
        for name, serializer in self.custom_serializers.items():
            if representation[name] is None:
                continue
            representation[name] = serializer.to_internal_value(representation[name])
        return self.model(**representation)

    def get_details_list_name(self, obj):
        lookup_field = self.details_lookup_field or self.lookup_field
        return obj[lookup_field]


class ModelBackupByName(ModelBackup):
    lookup_field = 'name'
