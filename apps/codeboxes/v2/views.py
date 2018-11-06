# coding=UTF8
from apps.codeboxes.v2.serializers import (
    CodeBoxScheduleSerializer,
    CodeBoxSerializer,
    CodeBoxTraceDetailSerializer,
    CodeBoxTraceSerializer,
    ScheduleTraceDetailSerializer,
    ScheduleTraceSerializer
)

from ..v1 import views as v1_views
from ..v1_1 import views as v1_1_views


class ScheduleTraceViewSet(v1_views.ScheduleTraceViewSet):
    list_deferred_fields = {'result'}
    serializer_class = ScheduleTraceSerializer
    serializer_detail_class = ScheduleTraceDetailSerializer


class CodeBoxTraceViewSet(v1_views.CodeBoxTraceViewSet):
    list_deferred_fields = {'result'}
    serializer_class = CodeBoxTraceSerializer
    serializer_detail_class = CodeBoxTraceDetailSerializer


class CodeBoxViewSet(v1_views.CodeBoxViewSet):
    serializer_class = CodeBoxSerializer

    def get_queryset(self):
        return super().get_queryset().select_related('socket')


class ScheduleViewSet(v1_1_views.ScheduleViewSet):
    serializer_class = CodeBoxScheduleSerializer
