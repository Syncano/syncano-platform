# coding=UTF8
from django.db import router

from apps.core.helpers import add_post_transaction_success_operation
from apps.instances.helpers import get_current_instance
from apps.triggers.models import Trigger

from .tasks import HandleTriggerEventTask


def launch_trigger(instance, serializer_class, event, signal, changes=None, **context):
    instance_pk = get_current_instance().pk

    if Trigger.match(instance_pk, event, signal):
        data = serializer_class(instance, excluded_fields=('links',), context=context).data
        if changes is not None:
            changes = changes.intersection(set(data.keys()))

        add_post_transaction_success_operation(HandleTriggerEventTask.delay,
                                               using=router.db_for_write(instance.__class__),
                                               instance_pk=instance_pk,
                                               event=event,
                                               signal=signal,
                                               data=data,
                                               changes=list(changes) if changes else None)


def launch_dataobject_trigger(instance, serializer_class, signal, data_serializer_class=None,
                              additional_changes=None, skip_user=False, **kwargs):
    additional_changes = additional_changes or set()
    changes = getattr(instance, 'changes', None) or set()
    changes |= additional_changes

    if not skip_user and instance._klass.is_user_profile:
        event = {'source': 'user'}
        launch_trigger(instance,
                       serializer_class=serializer_class,
                       event=event,
                       signal=signal,
                       changes=changes,
                       **kwargs)

    event = {'source': 'dataobject', 'class': instance._klass.name}
    launch_trigger(instance,
                   serializer_class=data_serializer_class or serializer_class,
                   event=event,
                   signal=signal,
                   changes=changes,
                   **kwargs)


def launch_user_trigger(instance, serializer_class, signal, **kwargs):
    event = {'source': 'user'}
    launch_trigger(instance,
                   serializer_class=serializer_class,
                   event=event,
                   signal=signal,
                   changes=getattr(instance, 'changes', None),
                   **kwargs)
