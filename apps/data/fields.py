# coding=UTF8
import rapidjson as json
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.postgres import fields as pg_fields
from django.core.files.base import File
from django.db import models
from django.db.models.fields.files import FieldFile

from apps.data.adapters import Json, PostGISAdapter
from apps.data.mixins import NoTrimWhitespaceMixin


class IncrementableIntegerField(models.IntegerField):
    serializer_class = 'apps.data.field_serializers.IncrementableIntegerFieldSerializer'


class IncrementableFloatField(models.FloatField):
    serializer_class = 'apps.data.field_serializers.IncrementableFloatFieldSerializer'


class ReferenceField(models.IntegerField):
    serializer_class = 'apps.data.field_serializers.ReferenceFieldSerializer'

    def __init__(self, target=None, *args, **kwargs):
        self.target = target
        super().__init__(*args, **kwargs)

    def get_serializer_kwargs(self):
        return {'target': self.target}

    def to_python(self, value):
        if not isinstance(value, int) and not value:
            return value
        return super().to_python(value)


class HStoreFileField(models.FileField):
    serializer_class = 'apps.data.field_serializers.HStoreFileFieldSerializer'

    def __init__(self, *args, **kwargs):
        self.old_value = None
        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        file = super(models.FileField, self).pre_save(model_instance, add)
        _files = model_instance._files

        # If we updating existing object and we got old_value set - delete that file.
        if model_instance.pk is not None and self.old_value and self.old_value._committed:
            self.old_value.delete(save=False)

        if file:
            if not file._committed:
                # Commit the file to storage prior to saving the model
                content = file.file
                _files[self.source] = content.size
                file.save(file.name, content, save=False)
        elif self.source in _files:
            del _files[self.source]
        return file

    def create_attr(self, instance, value):
        """
        Basically 1-1 what Django FileField descriptor __get__  does but it doesn't get/set instance values
        (as we have custom accessor in hstore field).
        """

        if isinstance(value, str) or value is None:
            value = self.attr_class(instance, self, value)
        elif isinstance(value, File) and not isinstance(value, FieldFile):
            file_copy = self.attr_class(instance, self, value.name)
            file_copy.file = value
            file_copy._committed = False
            value = file_copy
        elif isinstance(value, FieldFile) and not hasattr(value, 'field'):
            self.instance = instance
            self.field = self.field
            self.storage = self.field.storage
        return value

    def cleanup_attr(self, instance, new_value, old_value):
        """
        Save old value if it was a committed file so we delete it on pre_save.
        """

        new_value = self.create_attr(instance, new_value)
        if isinstance(old_value, FieldFile) and old_value._committed and new_value.name != old_value.name:
            self.old_value = old_value
        return new_value


class DateTimeField(models.DateTimeField):
    serializer_class = 'apps.data.field_serializers.DateTimeFieldSerializer'


class CharField(NoTrimWhitespaceMixin, models.CharField):
    pass


class TextField(NoTrimWhitespaceMixin, models.TextField):
    pass


class ArrayField(pg_fields.JSONField):
    serializer_class = 'apps.data.field_serializers.ArrayFieldSerializer'

    def get_prep_value(self, value):
        if value is not None:
            return Json(value)
        return value

    def get_hstore_prep_value(self, value):
        return self.get_prep_value(value)

    def get_internal_type(self):
        return 'JSONField'

    def to_python(self, value):
        # We need to provide this logic ourselves to convert jsonb on the fly from hstore
        # as we are using a more basic/custom descriptor as well.
        if isinstance(value, str):
            return json.loads(value)
        return value


class ObjectField(ArrayField):
    serializer_class = 'apps.data.field_serializers.ObjectFieldSerializer'


class NullBooleanField(models.NullBooleanField):
    serializer_class = 'apps.data.field_serializers.NullBooleanFieldSerializer'


class PointField(gis_models.PointField):
    serializer_class = 'apps.data.field_serializers.PointFieldSerializer'

    def to_python(self, value):
        # We need to provide this logic ourselves as hstore requires custom handling.
        # In this case we just do what GeometryField.from_db_value does.
        if value:
            return GEOSGeometry(value, srid=4326)
        return value

    def get_hstore_prep_value(self, value):
        if isinstance(value, str):
            value = GEOSGeometry(value, srid=4326)
        return PostGISAdapter(value, geography=self.geography)


class RelationField(pg_fields.ArrayField):
    serializer_class = 'apps.data.field_serializers.RelationFieldSerializer'

    def __init__(self, target=None, *args, **kwargs):
        self.target = target
        super().__init__(ReferenceField(), *args, **kwargs)

    def to_python(self, value):
        # Convert {} postgres array to python list as we are lacking typed fields in hstore.
        if isinstance(value, str):
            value = value[1:-1]
            # Treat empty postgres array as None
            if not value:
                return None
            value = [self.base_field.to_python(val) for val in value.split(',')]
        return value

    def get_hstore_prep_value(self, value):
        if isinstance(value, (list, tuple)):
            if not value:
                return None
            return '{%s}' % ','.join(map(str, value))
        return value

    def get_serializer_kwargs(self):
        return {'target': self.target}
