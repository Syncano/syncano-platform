# coding=UTF8
from rest_framework.fields import CharField

from apps.core.field_serializers import JSONField


class JSONFieldWithCutoff(JSONField):
    def __init__(self, cutoff, placeholder, *args, **kwargs):
        self.cutoff = cutoff
        self.placeholder = placeholder
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        if len(str(value)) > self.cutoff:
            return self.placeholder
        return super().to_representation(value)


class TruncatedCharField(CharField):
    truncated_suffix = '\n(...truncated...)'

    def __init__(self, cutoff, *args, **kwargs):
        self.cutoff = cutoff
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        value = super().to_representation(value)
        if isinstance(self.parent.instance, list) and len(value) > self.cutoff:
            return value[:self.cutoff - len(self.truncated_suffix)] + self.truncated_suffix
        return value
