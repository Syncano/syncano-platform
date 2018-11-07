# coding=UTF8
import re

import livefield
from django.core.validators import RegexValidator
from django.db import models
from django.utils.encoding import force_text
from django.utils.functional import curry
from django_hstore import descriptors as hstore_descriptors
from django_hstore import dict as hstore_dict
from django_hstore import hstore, virtual
from jsonfield import JSONField

from apps.core.helpers import import_class
from apps.data.helpers import convert_field_class_to_db_type
from apps.data.lookups import hstore_lookups


class VirtualField(virtual.VirtualField):
    pass


def create_virtual_field_class(base_field, **field_data):
    class VirtualField(HStoreVirtualMixin, base_field):
        # keep basefield info (added for django-rest-framework-hstore)
        __basefield__ = base_field

        def __init__(self, filter_index=False, order_index=False, *args, **kwargs):
            self.__dict__.update(field_data)
            self.filter_index = filter_index
            self.order_index = order_index
            super().__init__(*args, **kwargs)

        def deconstruct(self, *args, **kwargs):
            """
            specific for django 1.7 and greater (migration framework)
            """
            name, path, args, kwargs = super().deconstruct(*args, **kwargs)
            return name, path, args, {'default': kwargs.get('default')}

        def db_field(self, qn, connection, lhs=None):
            if lhs is not None and hasattr(lhs, 'alias'):
                alias = lhs.alias
            else:
                alias = self.model._meta.db_table

            return convert_field_class_to_db_type(field_source=self.source,
                                                  field_internal_type=self.get_internal_type(),
                                                  db_type=super(base_field, self).db_type(connection),
                                                  db_table=alias,
                                                  hstore_field_name=self.hstore_field_name)

        def get_lookup(self, name):
            if name in hstore_lookups:
                return hstore_lookups[name]
            return super().get_lookup(name)

    return VirtualField


def create_hstore_virtual_field(field_cls, kwargs, name, source, hstore_field_name):
    """
    returns an instance of an HStore virtual field which is mixed-in
    with the specified field class and initialized with the kwargs passed
    """
    if isinstance(field_cls, str):
        try:
            field_cls = getattr(models, field_cls)
        except AttributeError:
            field_cls = import_class(field_cls)

    if not issubclass(field_cls, models.Field):
        raise ValueError('Field must be either a django standard field or a subclass of django.db.models.Field.')

    base_field = field_cls

    VirtualField = create_virtual_field_class(base_field=base_field, hstore_field_name=hstore_field_name, source=source)

    if base_field == models.BooleanField:
        kwargs['null'] = False
        kwargs['default'] = False
    else:
        kwargs['default'] = kwargs.get('default')
        kwargs['null'] = kwargs.get('null', True)
        kwargs['blank'] = kwargs.get('blank', True)

    field = VirtualField(verbose_name=name, **kwargs)

    if field.default == models.fields.NOT_PROVIDED:
        field.default = ''

    return field


class HStoreVirtualMixin(virtual.HStoreVirtualMixin):
    def __get__(self, instance, instance_type=None):
        """
        retrieve value from hstore dictionary
        """
        if instance is None:
            raise AttributeError('Can only be accessed via instance.')

        hstore_dictionary = getattr(instance, self.hstore_field_name)
        value = hstore_dictionary.get(self.source, self.default)

        create_attr = getattr(self, 'create_attr', None)
        if create_attr:
            value = create_attr(instance, value)
            hstore_dictionary[self.source] = value

        return value

    def __set__(self, instance, value):
        """
        set value on hstore dictionary
        """

        hstore_dictionary = getattr(instance, self.hstore_field_name)

        cleanup_attr = getattr(self, 'cleanup_attr', None)
        if cleanup_attr:
            old_value = self.__get__(instance)
            if old_value:
                value = cleanup_attr(instance, value, old_value)

        hstore_dictionary[self.source] = value

    def contribute_to_class(self, cls, name):
        if self.choices:
            setattr(cls, 'get_%s_display' % self.name,
                    curry(cls._get_FIELD_display, field=self))
        self.attname = name
        self.name = name
        self.model = cls
        # setting column as none will tell django to not consider this a concrete field
        self.column = None
        # Connect myself as the descriptor for this field
        setattr(cls, name, self)
        # add field to class
        cls._meta.add_field(self, private=True)


class HStoreDict(hstore_dict.HStoreDict):
    def __setitem__(self, *args, **kwargs):
        """
        perform checks before setting the value of a key
        """
        # prepare *args
        args = (args[0], args[1])
        super(hstore_dict.HStoreDict, self).__setitem__(*args, **kwargs)


class HStoreDescriptor(hstore_descriptors.HStoreDescriptor):
    _DictClass = HStoreDict


class DictionaryField(hstore.DictionaryField):
    def reload_schema(self, schema):
        """
        Reload schema arbitrarily at run-time
        """
        if schema:
            self._validate_schema(schema)
            self.schema = schema
            self.schema_mode = True
            self.editable = False
        else:
            self.schema = None
            self.schema_mode = False
            self.editable = True
        # remove any existing virtual field
        self._remove_hstore_virtual_fields()
        # set new descriptor on model class
        setattr(self.model, self.name, HStoreDescriptor(self, schema_mode=self.schema_mode))
        # create virtual fields
        self._create_hstore_virtual_fields(self.model, self.name)

    def pre_save(self, model_instance, add):
        if hasattr(model_instance, '_hstore_virtual_fields'):
            for field in model_instance._hstore_virtual_fields.values():
                value = field.pre_save(model_instance, add)
                setattr(model_instance, field.attname, value)
        return super().pre_save(model_instance, add)

    def get_default(self):
        """
        Returns the default value for this field.
        """
        # if default defined
        if self.has_default():
            # if default is callable
            if callable(self.default):
                return self._init_dict(self.default())
            # if it's a dict
            elif isinstance(self.default, dict):
                return self._init_dict(self.default)
            # else just return it
            return self.default
        # default to empty dict
        return self._init_dict({})

    def get_prep_value(self, value):
        if isinstance(value, dict) and not isinstance(value, hstore_dict.HStoreDict):
            return self._init_dict(value)
        elif value is not None:
            if self.schema_mode:
                # Simplify for schema mode and add support for get_hstore_prep defined on field.
                hstore_fields = self.model._hstore_virtual_fields
                prep_values = {}

                for key, val in value.items():
                    if val is not None:
                        if key in hstore_fields and hasattr(hstore_fields[key], 'get_hstore_prep_value'):
                            val = hstore_fields[key].get_hstore_prep_value(val)
                        else:
                            val = force_text(val)
                    prep_values[key] = val
                return prep_values
            return {key: value.ensure_acceptable_value(val) for key, val in value.items()}

    def _init_dict(self, value):
        return HStoreDict(value, self, schema_mode=self.schema_mode)

    def contribute_to_class(self, cls, name):
        models.Field.contribute_to_class(self, cls, name)
        setattr(cls, self.name, HStoreDescriptor(self, schema_mode=self.schema_mode))

        if self.schema:
            self._create_hstore_virtual_fields(cls, name)

    def _create_hstore_virtual_fields(self, cls, hstore_field_name):
        """
        this methods creates all the virtual fields automatically by reading the schema attribute
        """
        if not self.schema_mode:
            return

        # add hstore_virtual_fields attribute to class
        if not hasattr(cls, '_hstore_virtual_fields'):
            cls._hstore_virtual_fields = {}

        # loop over all fields defined in schema
        for field in self.schema:
            source = field.get('source', field['name'])
            # initialize the virtual field by specifying the class, the kwargs and the hstore field name
            virtual_field = create_hstore_virtual_field(field['class'],
                                                        field.get('kwargs', {}),
                                                        field['name'],
                                                        source,
                                                        hstore_field_name)
            # this will call the contribute_to_class method in virtual.HStoreVirtualMixin
            cls.add_to_class(field['name'], virtual_field)
            # add this field to hstore_virtual_fields dict
            cls._hstore_virtual_fields[source] = virtual_field

    def _remove_hstore_virtual_fields(self):
        """ remove hstore virtual fields from class """
        cls = self.model
        # remove all hstore virtual fields related attributes
        if hasattr(cls, '_hstore_virtual_fields'):
            # remove attributes from class
            for field in cls._hstore_virtual_fields.values():
                delattr(cls, field.name)
            delattr(cls, '_hstore_virtual_fields')
        # remove  all hstore virtual fields from meta
        hstore_fields = []
        # get all the existing hstore virtual fields
        for field in getattr(cls._meta, 'private_fields'):
            if hasattr(field, 'hstore_field_name'):
                hstore_fields.append(field)
        # remove from meta
        for field in hstore_fields:
            getattr(cls._meta, 'private_fields').remove(field)
        # reset _meta.fields
        fields = [f for f in cls._meta.fields if not hasattr(f, 'hstore_field_name')]
        # cls._meta.fields.__class__ == ImmutableList
        cls._meta.fields = cls._meta.fields.__class__(fields)

    def value_to_string(self, obj):
        return self.value_from_object(obj)


class LowercaseFieldMixin:
    def to_python(self, value):
        value = super().to_python(value)
        if isinstance(value, str):
            return value.lower().strip()
        return value


class LowercaseEmailField(LowercaseFieldMixin, models.EmailField):
    pass


class LowercaseCharField(LowercaseFieldMixin, models.CharField):
    pass


class StrippedSlugField(LowercaseFieldMixin, models.CharField):
    default_validators = [
        RegexValidator(regex=re.compile(r'^[a-z]'),
                       message='Value has to start with a letter.'),
        RegexValidator(regex=re.compile(r'[a-z0-9]$'),
                       message='Value has to end with a letter or a number.')
    ]

    def __init__(self, allow_hyphen=True, allow_slash=False, allow_underscore=True, allow_dots=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = ['letters', 'numbers']
        allowed_chars = r'a-z0-9'

        if allow_underscore:
            allowed.append('underscores')
            allowed_chars += r'_'
        if allow_hyphen:
            allowed.append('hyphens')
            allowed_chars += r'\-'
        if allow_slash:
            allowed.append('slashes')
            allowed_chars += r'/'
        if allow_dots:
            allowed.append('dots')
            allowed_chars += r'\.'

        validator = RegexValidator(regex=re.compile(r'^[{}]*$'.format(allowed_chars)),
                                   message='Enter a valid value consisting of '
                                           '{}.' .format(', '.join(allowed)))
        self.validators.append(validator)

    def to_python(self, value):
        value = super().to_python(value)
        if isinstance(value, str):
            return value.strip()
        return value


class LiveField(livefield.LiveField):
    def __init__(self, db_index=False, *args, **kwargs):
        # Stupid LiveField doesn't allow db_index parameter so we need to override it's init
        models.NullBooleanField.__init__(self, default=True, null=True, db_index=db_index)


class NullableJSONField(JSONField):
    """
    JSONField that treats null the same as default value provided.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(default=kwargs.pop('default', None), null=True, blank=True)

    def pre_init(self, value, obj):
        value = super().pre_init(value, obj)
        if value is None:
            return self.get_default()
        return value
