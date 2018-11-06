# coding=UTF8
from apps.instances.v1_1 import views as v1_1_views
from apps.instances.v2.serializers import InstanceDetailSerializer, InstanceSerializer


class InstanceViewSet(v1_1_views.InstanceViewSet):
    serializer_class = InstanceSerializer
    serializer_detail_class = InstanceDetailSerializer
