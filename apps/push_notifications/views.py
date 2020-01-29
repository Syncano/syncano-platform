# coding=UTF8
from django_filters.rest_framework import DjangoFilterBackend
from rest_condition import And, Or
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.permissions import AdminHasPermissions
from apps.apikeys.permissions import IsApiKeyAccess, IsApiKeyAllowingAnonymousRead, IsApiKeyIgnoringAcl
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.views import LinksView
from apps.instances.mixins import InstanceBasedMixin
from apps.push_notifications.mixins import SendPushMessageMixin
from apps.users.permissions import HasUser

from .filters import APNSDeviceFilter, GCMDeviceFilter
from .models import APNSConfig, APNSDevice, APNSMessage, GCMConfig, GCMDevice, GCMMessage
from .permissions import HasDevicePermission
from .serializers import (
    APNSConfigSerializer,
    APNSDeviceDetailSerializer,
    APNSDeviceSerializer,
    APNSMessageSerializer,
    GCMConfigSerializer,
    GCMDeviceDetailSerializer,
    GCMDeviceSerializer,
    GCMMessageSerializer,
    RemoveAPNSCertificateSerializer
)


class BaseConfigViewSet(InstanceBasedMixin,
                        mixins.RetrieveModelMixin,
                        mixins.UpdateModelMixin,
                        viewsets.GenericViewSet):

    def get_object(self):
        queryset = self.get_queryset()
        obj = generics.get_object_or_404(queryset)
        self.check_object_permissions(self.request, obj)
        return obj


class GCMConfigViewSet(BaseConfigViewSet):
    model = GCMConfig
    queryset = GCMConfig.objects.all()
    serializer_class = GCMConfigSerializer


class APNSConfigViewSet(BaseConfigViewSet):
    model = APNSConfig
    queryset = APNSConfig.objects.all()
    serializer_class = APNSConfigSerializer

    @detail_route(methods=['post'])
    def remove_certificate(self, request, *args, **kwargs):
        config = self.get_object()
        serializer = RemoveAPNSCertificateSerializer(data=request.data)
        if serializer.is_valid():
            for key, val in serializer.data.items():
                if val:
                    setattr(config, key, None)
            config.save()
            serializer = APNSConfigSerializer(instance=config, context=self.get_serializer_context())
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BaseDeviceViewSet(InstanceBasedMixin,
                        DetailSerializerMixin,
                        SendPushMessageMixin,
                        viewsets.ModelViewSet):
    filter_backends = (DjangoFilterBackend, )
    permission_classes = (
        OwnerInGoodStanding,
        Or(
            # Check admin permissions first
            AdminHasPermissions,
            And(
                # Otherwise when we're dealing with api key access
                IsApiKeyAccess,
                Or(
                    # Force access when ignoring acl
                    IsApiKeyIgnoringAcl,
                    # Force access when allow annonymous read
                    IsApiKeyAllowingAnonymousRead,
                    And(
                        # Or if user is associated - check relevant Device permissions
                        HasUser,
                        HasDevicePermission,
                    )
                )
            )
        )
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.auth and not self.request.auth.ignore_acl and self.request.auth_user:
            queryset = queryset.filter(user=self.request.auth_user)
        return queryset


class GCMDeviceViewSet(BaseDeviceViewSet):
    model = GCMDevice
    queryset = GCMDevice.objects.all()
    serializer_class = GCMDeviceSerializer
    serializer_detail_class = GCMDeviceDetailSerializer
    message_serializer = GCMMessageSerializer
    lookup_field = 'registration_id'
    filterset_class = GCMDeviceFilter


class APNSDeviceViewSet(BaseDeviceViewSet):
    model = APNSDevice
    queryset = APNSDevice.objects.all()
    serializer_class = APNSDeviceSerializer
    serializer_detail_class = APNSDeviceDetailSerializer
    message_serializer = APNSMessageSerializer
    lookup_field = 'registration_id'
    filterset_class = APNSDeviceFilter


class GCMMessageViewSet(InstanceBasedMixin,
                        mixins.CreateModelMixin,
                        mixins.RetrieveModelMixin,
                        mixins.ListModelMixin,
                        viewsets.GenericViewSet):
    model = GCMMessage
    queryset = GCMMessage.objects.all()
    serializer_class = GCMMessageSerializer


class APNSMessageViewSet(InstanceBasedMixin,
                         mixins.CreateModelMixin,
                         mixins.RetrieveModelMixin,
                         mixins.ListModelMixin,
                         viewsets.GenericViewSet):
    model = APNSMessage
    queryset = APNSMessage.objects.all()
    serializer_class = APNSMessageSerializer


class TopPushNotificationLinkView(InstanceBasedMixin, LinksView):

    def _generate_gcm_links(self):
        return {
            'devices': reverse('gcm-devices-list', args=(self.request.instance.name,), request=self.request),
            'messages': reverse('gcm-messages-list', args=(self.request.instance.name,), request=self.request),
            'config': reverse('gcm-config', args=(self.request.instance.name,), request=self.request),
        }

    def _generate_apns_links(self):
        return {
            'devices': reverse('apns-devices-list', args=(self.request.instance.name,), request=self.request),
            'messages': reverse('apns-messages-list', args=(self.request.instance.name,), request=self.request),
            'config': reverse('apns-config', args=(self.request.instance.name,), request=self.request),
        }

    def generate_links(self):
        return {
            'gcm': {
                'uri': reverse('gcm-push', args=(self.request.instance.name,), request=self.request),
                'links': self._generate_gcm_links(),
            },
            'apns': {
                'uri': reverse('apns-push', args=(self.request.instance.name,), request=self.request),
                'links': self._generate_apns_links(),
            }
        }


class GcmPushNotificationLinkView(TopPushNotificationLinkView):
    def generate_links(self):
        return self._generate_gcm_links()


class APNSPushNotificationLinkView(TopPushNotificationLinkView):
    def generate_links(self):
        return self._generate_apns_links()
