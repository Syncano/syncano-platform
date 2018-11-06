# coding=UTF8
import django_filters

from apps.admins.models import Admin


class AdminViewFilter(django_filters.FilterSet):
    email = django_filters.CharFilter(name="email", lookup_expr="istartswith")

    class Meta:
        model = Admin
        fields = ['email', 'first_name', 'last_name']
