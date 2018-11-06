# coding=UTF8
from django.conf import settings
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.permissions import AdminHasPermissions
from apps.billing.models import AdminLimit
from apps.billing.permissions import OwnerInGoodStanding
from apps.codeboxes.exceptions import LegacyCodeBoxDisabled, ScheduleCountExceeded
from apps.codeboxes.models import CodeBox, CodeBoxSchedule, CodeBoxTrace, ScheduleTrace
from apps.codeboxes.permissions import ProtectScheduleAccess, ProtectScriptAccess
from apps.codeboxes.runtimes import RUNTIMES_META
from apps.codeboxes.tasks import CodeBoxTask
from apps.codeboxes.v1.serializers import (
    CodeBoxRunSerializer,
    CodeBoxScheduleSerializer,
    CodeBoxSerializer,
    CodeBoxTraceDetailSerializer,
    CodeBoxTraceSerializer,
    ScheduleTraceDetailSerializer,
    ScheduleTraceSerializer
)
from apps.core.mixins.views import AutocompleteMixin, CacheableObjectMixin, NestedViewSetMixin, ValidateRequestSizeMixin
from apps.instances.mixins import InstanceBasedMixin
from apps.instances.models import Instance
from apps.redis_storage import views as redis_views


class CodeBoxViewSet(CacheableObjectMixin,
                     ValidateRequestSizeMixin,
                     AutocompleteMixin,
                     InstanceBasedMixin,
                     viewsets.ModelViewSet):
    model = CodeBox
    queryset = CodeBox.objects.all()
    serializer_class = CodeBoxSerializer
    autocomplete_field = 'label'
    permission_classes = (
        AdminHasPermissions,
        OwnerInGoodStanding,
        ProtectScriptAccess,
    )

    @detail_route(methods=['post'],
                  serializer_class=CodeBoxRunSerializer,
                  request_limit=settings.CODEBOX_PAYLOAD_SIZE_LIMIT)
    def run(self, request, *args, **kwargs):
        if not settings.LEGACY_CODEBOX_ENABLED:
            raise LegacyCodeBoxDisabled()

        codebox = self.get_object()
        instance_pk = request.instance.pk
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            additional_args = serializer.data['payload']
            as_staff = request.staff_user is not None
            trace = CodeBoxTrace.create(codebox=codebox, executed_by_staff=as_staff)

            CodeBoxTask.delay(codebox.id, instance_pk, additional_args=additional_args, trace_pk=trace.pk)
            # Workaround for links
            self.kwargs['codebox'] = codebox
            return Response(CodeBoxTraceSerializer(trace, context=self.get_serializer_context()).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ScheduleViewSet(InstanceBasedMixin,
                      viewsets.ModelViewSet):
    model = CodeBoxSchedule
    queryset = CodeBoxSchedule.objects.all()
    serializer_class = CodeBoxScheduleSerializer
    permission_classes = (
        AdminHasPermissions,
        OwnerInGoodStanding,
        ProtectScheduleAccess,
    )

    def perform_create(self, serializer):
        # Lock on instance for the duration of transaction to avoid race conditions
        with transaction.atomic():
            Instance.objects.select_for_update().get(pk=self.request.instance.pk)
            schedule_limit = AdminLimit.get_for_admin(self.request.instance.owner_id).get_schedules_count()
            if CodeBoxSchedule.objects.count() >= schedule_limit:
                raise ScheduleCountExceeded(schedule_limit)
            object = serializer.save()
            object.schedule_next()

    def perform_update(self, serializer):
        obj = serializer.save()
        obj.schedule_next()


class TraceViewSet(InstanceBasedMixin,
                   NestedViewSetMixin,
                   redis_views.ReadOnlyModelViewSet):
    list_deferred_fields = None

    def list(self, request, *args, **kwargs):
        # Some fields in list view shouldn't be shown, defer them
        self.kwargs['deferred_fields'] = self.list_deferred_fields
        return super().list(request, *args, **kwargs)


class ScheduleTraceViewSet(DetailSerializerMixin, TraceViewSet):
    model = ScheduleTrace
    serializer_class = ScheduleTraceSerializer
    serializer_detail_class = ScheduleTraceDetailSerializer


class CodeBoxTraceViewSet(DetailSerializerMixin, TraceViewSet):
    model = CodeBoxTrace
    serializer_class = CodeBoxTraceSerializer
    serializer_detail_class = CodeBoxTraceDetailSerializer


class RuntimeViewSet(InstanceBasedMixin, viewsets.ViewSet):
    model = CodeBox  # to use the same permissions as CodeBox

    def list(self, request, *args, **kwargs):
        """List available CodeBox runtimes"""
        return Response(RUNTIMES_META)
