# coding=UTF8
from rest_framework import viewsets
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.permissions import AdminHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.codeboxes.v1.views import TraceViewSet
from apps.core.mixins.views import AtomicMixin
from apps.instances.mixins import InstanceBasedMixin
from apps.triggers.models import Trigger, TriggerTrace
from apps.triggers.permissions import ProtectTriggerAccess
from apps.triggers.v1.serializers import TriggerSerializer, TriggerTraceDetailSerializer, TriggerTraceSerializer


class TriggerViewSet(AtomicMixin,
                     InstanceBasedMixin,
                     viewsets.ModelViewSet):
    model = Trigger
    queryset = Trigger.objects.select_related('codebox').filter(event__source='dataobject')
    serializer_class = TriggerSerializer
    permission_classes = (
        AdminHasPermissions,
        OwnerInGoodStanding,
        ProtectTriggerAccess,
    )


class TriggerTraceViewSet(DetailSerializerMixin, TraceViewSet):
    model = TriggerTrace
    serializer_class = TriggerTraceSerializer
    serializer_detail_class = TriggerTraceDetailSerializer
