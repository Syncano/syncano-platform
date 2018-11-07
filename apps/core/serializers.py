# coding=UTF8
from rest_framework import serializers

from apps.core.mixins.serializers import AclMixin


class NewNameSerializer(serializers.Serializer):
    new_name = serializers.CharField()


class EndpointAclSerializer(AclMixin, serializers.Serializer):
    is_endpoint_acl = True
