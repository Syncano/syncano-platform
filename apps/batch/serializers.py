# coding=UTF8
from rest_framework import serializers

from apps.batch.validators import PathValidator
from apps.core.field_serializers import JSONField, LowercaseCharField
from apps.core.validators import validate_batch_body


class BatchRequestSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=('GET', 'POST', 'PUT', 'PATCH', 'DELETE'))
    path = LowercaseCharField(max_length=8192, validators=[PathValidator()])
    body = JSONField(default={}, validators=[validate_batch_body])


class BatchSerializer(serializers.Serializer):
    requests = BatchRequestSerializer(many=True)
