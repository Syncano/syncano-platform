# coding=UTF8
from apps.codeboxes.v1_1.serializers import CodeBoxScheduleSerializer

from ..v1 import views as v1_views


class ScheduleViewSet(v1_views.ScheduleViewSet):
    serializer_class = CodeBoxScheduleSerializer
