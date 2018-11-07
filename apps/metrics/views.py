from django.core.exceptions import ValidationError
from django.db.models import DateField, DateTimeField, Sum
from rest_framework import permissions
from rest_framework.mixins import ListModelMixin
from rest_framework.reverse import reverse
from rest_framework.viewsets import GenericViewSet

from apps.core.helpers import is_query_param_true
from apps.core.mixins.views import AtomicMixin
from apps.core.views import LinksView
from apps.metrics.exceptions import IncorrectQueryValue

from .models import DayAggregate, HourAggregate
from .serializers import DayAggregateSerializer, HourAggregateSerializer


class StatsLinksView(LinksView):
    def generate_links(self):
        return {
            'hourly': reverse('hour-aggregate-list', request=self.request),
            'daily': reverse('day-aggregate-list', request=self.request),
        }


class HourlyStatsViewSet(AtomicMixin,
                         ListModelMixin,
                         GenericViewSet):
    model = HourAggregate
    queryset = HourAggregate.objects.all()
    serializer_class = HourAggregateSerializer
    permission_classes = (
        permissions.IsAuthenticated,
    )
    range_field = DateTimeField()
    paginate_query_params = ('start', 'end', 'source', 'instance')

    def get_datefield(self, field_name):
        value = self.request.query_params.get(field_name)
        if value:
            try:
                return self.range_field.to_python(value)
            except ValidationError as ex:
                raise IncorrectQueryValue(ex.messages[0], field_name)

    def parse_source(self, value):
        value = value.lower()
        found = next((src for src in self.model.SOURCES.as_choices() if src[0] == value), None)
        if not found:
            raise IncorrectQueryValue(field='source')
        return value

    def get_queryset(self):
        qs = super().get_queryset().filter(admin=self.request.user).order_by('timestamp')

        # Don't filter retrieve
        if self.action != 'list':
            return qs

        start = self.get_datefield('start')
        if start:
            qs = qs.filter(timestamp__gte=start)

        end = self.get_datefield('end')
        if end:
            qs = qs.filter(timestamp__lte=end)

        source = self.request.query_params.get('source')
        if source and self.parse_source(source):
            qs = qs.filter(source=source)

        if is_query_param_true(self.request, 'total'):
            qs = qs.values('timestamp', 'source').annotate(value=Sum('value'))
            self.pagination_enabled = False
        else:
            instance = self.request.query_params.get('instance')
            if instance:
                qs = qs.filter(instance_name=instance)
        return qs


class DailyStatsViewSet(HourlyStatsViewSet):
    model = DayAggregate
    queryset = DayAggregate.objects.all()
    serializer_class = DayAggregateSerializer
    range_field = DateField()
