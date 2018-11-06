# coding=UTF8
from collections import namedtuple

import rapidjson as json
from django.contrib.postgres.fields import ArrayField, HStoreField
from django.db import models

from apps.codeboxes.models import CodeBox, Trace
from apps.core.abstract_models import (
    CacheableAbstractModel,
    CreatedUpdatedAtAbstractModel,
    LabelDescriptionAbstractModel,
    TrackChangesAbstractModel
)
from apps.core.helpers import Cached
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS
from apps.triggers.querysets import TriggerQuerySet


class Trigger(CacheableAbstractModel, CreatedUpdatedAtAbstractModel, LabelDescriptionAbstractModel,
              TrackChangesAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    codebox = models.ForeignKey(CodeBox, related_name='event_tasks', on_delete=models.CASCADE)

    event = HStoreField()
    signals = ArrayField(models.TextField())
    socket = models.ForeignKey('sockets.Socket', blank=True, null=True, default=None, on_delete=models.CASCADE)

    objects = TriggerQuerySet().as_manager()

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'Trigger[id=%s, label=%s]' % (
            self.pk,
            self.label,
        )

    @property
    def klass(self):
        # Needed to maintain API v1-v1.1 compatibility.
        return namedtuple('Klass', ['name'])(name=self.event['class'])

    @klass.setter
    def klass(self, value):
        self.event = {'source': 'dataobject', 'class': value.name}

    @property
    def signal(self):
        # Needed to maintain API v1-v1.1 compatibility.
        return 'post_{}'.format(self.signals[0])

    @signal.setter
    def signal(self, value):
        self.signals = [value[5:]]  # cut 5 first letters (post_)

    @classmethod
    def match_cached(cls, instance_pk, event, signal):
        def _match_cached(signal):
            return cls.objects.match(event, signal)

        return Cached(_match_cached,
                      args=(signal,),
                      key='Trigger.Match',
                      version_key='i=%d;e=%s' % (instance_pk, json.dumps(event, sort_keys=True)))

    @classmethod
    def match(cls, instance_pk, event, signal):
        return cls.match_cached(instance_pk, event, signal).get()

    @classmethod
    def invalidate_match(cls, instance_pk, event):
        return cls.match_cached(instance_pk, event, None).invalidate()


class TriggerTrace(Trace):
    list_template_args = '{instance.id}:{trigger.id}'
