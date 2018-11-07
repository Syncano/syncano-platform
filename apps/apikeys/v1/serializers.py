from rest_framework import serializers

from apps.apikeys.models import ApiKey
from apps.core.mixins.serializers import DynamicFieldsMixin, HyperlinkedMixin
from apps.data.v1.serializers import HStoreSerializer


class ApiKeySerializer(DynamicFieldsMixin,
                       HyperlinkedMixin,
                       HStoreSerializer):
    hyperlinks = (
        ('self', 'apikey-detail', ('instance.name', 'pk', )),
        ('reset_key', 'apikey-reset-key', ('instance.name', 'pk', )),
    )

    api_key = serializers.ReadOnlyField(source='key')

    class Meta:
        model = ApiKey
        fields = ('id', 'description', 'api_key', 'ignore_acl',
                  'allow_user_create', 'allow_group_create', 'allow_anonymous_read', 'created_at')

    def to_internal_value(self, data):
        reverted_data = super().to_internal_value(data)
        if reverted_data is not None:
            reverted_data['instance'] = self.context['request'].instance
        return reverted_data
