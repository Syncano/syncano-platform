# coding=UTF8
from apps.triggers.v1 import views as v1_views
from apps.triggers.v1_1.serializers import TriggerSerializer


class TriggerViewSet(v1_views.TriggerViewSet):
    serializer_class = TriggerSerializer
