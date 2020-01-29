# coding=UTF8
import django_filters
from django_filters.filters import Filter, UUIDFilter

from apps.core.filter_fields import LowercaseBooleanFilter
from apps.push_notifications.forms import HexIntegerFormField
from apps.users.models import User

from .models import APNSDevice, GCMDevice


class BaseDeviceFilter(django_filters.FilterSet):
    device_id = django_filters.CharFilter(lookup_expr='exact')
    user = django_filters.ModelChoiceFilter(queryset=User.objects.all())
    is_active = LowercaseBooleanFilter()

    class Meta:
        fields = ['device_id', 'is_active', 'user']


class HexIntegerFilter(Filter):
    field_class = HexIntegerFormField


class GCMDeviceFilter(BaseDeviceFilter):
    device_id = HexIntegerFilter(lookup_expr='exact')

    class Meta(BaseDeviceFilter.Meta):
        model = GCMDevice


class APNSDeviceFilter(BaseDeviceFilter):
    device_id = UUIDFilter(lookup_expr='exact')

    class Meta(BaseDeviceFilter.Meta):
        model = APNSDevice
