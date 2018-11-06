# coding=UTF8
from apps.hosting.v1_1 import views as v1_1_views
from apps.hosting.v2.serializers import HostingDetailSerializer, HostingSerializer


class HostingViewSet(v1_1_views.HostingViewSet):
    lookup_field = 'name'
    lookup_value_regex = '[^/]+'
    serializer_class = HostingSerializer
    serializer_detail_class = HostingDetailSerializer
    hosting_serializer_class = HostingSerializer

    def get_queryset(self):
        return super().get_queryset().select_related('socket')


class HostingFileViewSet(v1_1_views.HostingFileViewSet):
    pass
