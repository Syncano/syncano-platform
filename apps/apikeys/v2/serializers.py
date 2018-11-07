from apps.apikeys.v1 import serializers as v1_serializers


class ApiKeySerializer(v1_serializers.ApiKeySerializer):
    class Meta(v1_serializers.ApiKeySerializer.Meta):
        fields = ('id', 'description', 'api_key', 'ignore_acl', 'created_at')
