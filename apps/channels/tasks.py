# coding=UTF8
import json

from munch import Munch
from settings.celeryconf import register_task

from apps.channels.models import Change
from apps.channels.v1.serializers import ChangeSerializer
from apps.core.helpers import redis
from apps.core.tasks import InstanceBasedTask


@register_task
class GetChangeTask(InstanceBasedTask):
    def run(self, result_key, channel_pk, last_id, channel_room=None, current_last_id=None, limit=1, **kwargs):
        change_list = Change.list(ordering='asc', min_pk=last_id + 1, max_pk=current_last_id, limit=limit,
                                  channel=Munch(id=channel_pk), room=channel_room)

        for change in change_list:
            # Publish serialized change
            message = ChangeSerializer(change, excluded_fields=('links', 'room',)).data
            message = json.dumps(message)
            redis.publish(result_key, message)
        redis.publish(result_key, '')
