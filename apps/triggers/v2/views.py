# coding=UTF8
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import list_route
from rest_framework.response import Response

from apps.core.mixins.views import ValidateRequestSizeMixin
from apps.instances.helpers import get_current_instance
from apps.triggers.models import Trigger
from apps.triggers.tasks import HandleTriggerEventTask
from apps.triggers.v1 import views as v1_views
from apps.triggers.v1_1 import views as v1_1_views
from apps.triggers.v2.serializers import (
    TriggerEmitSerializer,
    TriggerSerializer,
    TriggerTraceDetailSerializer,
    TriggerTraceSerializer
)


class TriggerViewSet(ValidateRequestSizeMixin, v1_1_views.TriggerViewSet):
    serializer_class = TriggerSerializer
    queryset = Trigger.objects.select_related('codebox')

    @list_route(methods=['post'], serializer_class=TriggerEmitSerializer,
                request_limit=settings.TRIGGER_PAYLOAD_SIZE_LIMIT)
    def emit(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        event = {'source': 'custom'}
        signal = serializer.data['signal']
        payload = serializer.data['payload']

        if Trigger.match(get_current_instance().pk, event, signal):
            HandleTriggerEventTask.delay(instance_pk=get_current_instance().pk,
                                         event=event,
                                         signal=signal,
                                         data=payload)
            ret = status.HTTP_202_ACCEPTED
        else:
            ret = status.HTTP_204_NO_CONTENT
        return Response(status=ret)


class TriggerTraceViewSet(v1_views.TriggerTraceViewSet):
    list_deferred_fields = {'result'}
    serializer_class = TriggerTraceSerializer
    serializer_detail_class = TriggerTraceDetailSerializer
