# coding=UTF8
from datetime import timedelta

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from psycopg2._range import DateRange
from rest_framework import status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response

from apps.admins.models import Admin
from apps.admins.serializers import AdminForStaffSerializer
from apps.billing.models import Profile, Subscription
from apps.billing.serializers import SubscriptionSerializer
from apps.controlpanel.serializer import ExtendSerializer
from apps.core.mixins.views import AtomicMixin

from .filters import AdminViewFilter
from .permissions import IsStaffUser


class AdminViewSet(AtomicMixin, viewsets.ReadOnlyModelViewSet):
    model = Admin
    queryset = Admin.objects.all()
    serializer_class = AdminForStaffSerializer
    permission_classes = (IsStaffUser,)
    filter_backends = (DjangoFilterBackend,)
    filter_class = AdminViewFilter

    @detail_route(methods=['post'], serializer_class=ExtendSerializer)
    def extend_builder_plan(self, request, *args, **kwargs):
        admin = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            try:
                subscription = Profile.get_active_subscription(admin.id)
            except Subscription.DoesNotExist:
                return Response({'detail': 'No active subscription.'}, status=status.HTTP_400_BAD_REQUEST)

            if Subscription.objects.filter(admin=admin, range__gt=subscription.range).exists():
                return Response({'detail': 'Current subscription is not a newest one.'},
                                status=status.HTTP_400_BAD_REQUEST)

            if subscription.plan.name != 'builder':
                return Response({'detail': 'Current subscription is not on a builder plan.'},
                                status=status.HTTP_400_BAD_REQUEST)

            now = timezone.now().date()
            subscription.range = DateRange(subscription.start, now + timedelta(days=serializer.data['days']))
            subscription.save()
            return Response(SubscriptionSerializer(subscription, context=self.get_serializer_context()).data,
                            status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
