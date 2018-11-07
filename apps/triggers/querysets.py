# coding=UTF8
from django.db.models import QuerySet


class TriggerQuerySet(QuerySet):
    def match(self, event, signal):
        return self.filter(event__contains=event, signals__contains=[signal])
