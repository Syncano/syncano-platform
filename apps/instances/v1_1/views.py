# coding=UTF8

from apps.instances.v1 import views as v1_views
from apps.instances.v1_1.serializers import InstanceDetailSerializer, InstanceSerializer


class InstanceViewSet(v1_views.InstanceViewSet):
    serializer_class = InstanceSerializer
    serializer_detail_class = InstanceDetailSerializer
