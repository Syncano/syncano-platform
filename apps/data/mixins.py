# coding=UTF8
import rapidjson as json
from django.core.exceptions import ValidationError
from rest_framework.fields import get_attribute

from apps.core.helpers import Cached


class ObjectSchemaProcessViewMixin:
    def initial(self, request, *args, **kwargs):
        if getattr(self, 'klass', None):
            self.model.load_klass(self.klass)
        return super().initial(request, *args, **kwargs)


class OpDictFieldSerializerMixin:
    supported_ops = set()

    def process_value_operation(self, value, op_dict):
        raise NotImplementedError('Subclasses must provide a process_value_operation method.')  # pragma: no cover

    def to_internal_value(self, data):
        if self.parent.instance and data:
            data_obj = data
            if isinstance(data_obj, str):
                try:
                    data_obj = json.loads(data_obj)
                except ValueError:
                    pass
            if isinstance(data_obj, dict):
                cur_value = get_attribute(self.parent.instance, self.source_attrs)

                for key in data_obj.keys():
                    if key not in self.supported_ops:
                        raise ValidationError(self.error_messages['invalid'])

                data = self.process_value_operation(cur_value, data_obj)

        return super().to_internal_value(data)


class IncrementableFieldSerializerMixin(OpDictFieldSerializerMixin):
    INCREMENT_OP = '_increment'

    supported_ops = {INCREMENT_OP}

    def process_value_operation(self, value, op_dict):
        value = value or 0
        increment = self.to_internal_value(op_dict[self.INCREMENT_OP])
        return value + increment


class NoTrimWhitespaceMixin:
    def get_serializer_kwargs(self):
        return {'trim_whitespace': False}


class RelatedModelFieldSerializerMixin:
    def get_model_and_filter_kwargs(self):
        if self.target == 'user':
            from apps.users.models import User

            return User, {}
        else:
            from apps.data.models import Klass, DataObject

            if self.target == 'self':
                klass = self.context['view'].klass
            else:

                try:
                    klass = Cached(Klass, kwargs=dict(name=self.target)).get()
                except Klass.DoesNotExist:
                    raise ValidationError('Target class does not exist.')

            return DataObject, {'_klass_id': klass.pk}
