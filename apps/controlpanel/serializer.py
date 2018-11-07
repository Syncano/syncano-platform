# coding=UTF8
from rest_framework import serializers
from rest_framework.serializers import Serializer


class ExtendSerializer(Serializer):
    days = serializers.IntegerField(min_value=1, max_value=365, default=30)
