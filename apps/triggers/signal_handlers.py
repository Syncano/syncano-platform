# coding=UTF8
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.signals import apiview_view_processed
from apps.data.models import DataObject
from apps.instances.helpers import get_current_instance
from apps.triggers.helpers import launch_dataobject_trigger, launch_user_trigger
from apps.triggers.models import Trigger
from apps.users.models import User
from apps.users.signals import social_user_created


@receiver(apiview_view_processed, sender=DataObject, dispatch_uid='triggers_data_apiview_processed_handler')
def data_apiview_processed_handler(sender, view, instance, action, **kwargs):
    """
    Handler used for DataObject and in v2+ also for Users (which are DataObject-based).
    Action possible values: create/update/delete.
    """

    changes = None
    if hasattr(view, 'data_serializer_class'):
        # if view has data_serializer_class - we're dealing with a user view
        changes = getattr(instance.owner, 'changes', None)

    launch_dataobject_trigger(instance=instance,
                              serializer_class=getattr(view, 'full_serializer_class', view.serializer_class),
                              signal=action,
                              data_serializer_class=getattr(view, 'data_serializer_class', None),
                              view=view,
                              additional_changes=changes)


@receiver(apiview_view_processed, sender=User, dispatch_uid='triggers_user_apiview_processed_handler')
def user_apiview_processed_handler(sender, view, instance, action, **kwargs):
    """
    Handler used for pre-v2 (v1 and v1.1) Users.
    Action possible values: create/update/delete which maps 1-1 to signal.
    """

    # Launch trigger for User
    launch_user_trigger(instance=instance,
                        serializer_class=view.serializer_class,
                        signal=action,
                        view=view)

    # Launch trigger for DataObject (user's profile)
    launch_dataobject_trigger(instance=instance.profile,
                              serializer_class=view.data_serializer_class,
                              signal=action,
                              view=view,
                              additional_changes=getattr(instance, 'changes', None),
                              skip_user=True)


@receiver(social_user_created, sender=User, dispatch_uid='triggers_social_user_created_handler')
def social_user_created_handler(sender, view, instance, **kwargs):
    # Launch trigger for User
    launch_user_trigger(instance=instance,
                        serializer_class=view.response_serializer_class,
                        signal='create',
                        view=view)

    # Launch trigger for DataObject (user's profile)
    launch_dataobject_trigger(instance=instance.profile,
                              serializer_class=view.data_serializer_class,
                              signal='create',
                              view=view,
                              skip_user=True)


def invalidate_trigger_match(event):
    instance_id = get_current_instance().id
    Trigger.invalidate_match(instance_id, event)


@receiver(post_save, sender=Trigger, dispatch_uid='trigger_post_save_handler')
def trigger_post_save_handler(sender, instance, created, **kwargs):
    # Invalidate cached match
    if not created:
        if instance.has_changed('event'):
            invalidate_trigger_match(instance.old_value('event'))
            invalidate_trigger_match(instance.event)
        elif instance.has_changed('signals'):
            invalidate_trigger_match(instance.event)
    else:
        invalidate_trigger_match(instance.event)


@receiver(post_delete, sender=Trigger, dispatch_uid='trigger_post_delete_handler')
def trigger_post_delete_handler(sender, instance, **kwargs):
    # Invalidate cached match
    invalidate_trigger_match(instance.event)
