from rest_framework.serializers import ModelSerializer

from apps.core.field_serializers import JSONField
from apps.core.validators import validate_config
from apps.instances.models import Instance


class InstanceConfigSerializer(ModelSerializer):
    config = JSONField(validators=[validate_config], default={})

    class Meta:
        model = Instance
        fields = ('config',)
