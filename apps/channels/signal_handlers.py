# coding=UTF8
from django.dispatch import receiver

from apps.channels.helpers import create_author_dict
from apps.channels.models import Change, Channel
from apps.core.signals import apiview_view_processed, post_tenant_migrate
from apps.data.models import DataObject


@receiver(apiview_view_processed, sender=DataObject, dispatch_uid='channels_data_apiview_processed_handler')
def data_apiview_processed_handler(sender, view, instance, action, **kwargs):
    if instance.channel_id is None:
        return

    action = Change.ACTIONS(action).value
    request = view.request
    channel = instance.channel
    room = instance.channel_room

    view.check_channel_permission(request, channel)
    author = create_author_dict(request)
    metadata = {'type': 'object', 'class': view.klass.name}
    changes = getattr(instance, 'changes', None)
    if changes is not None:
        changes.add('id')

    payload = view.serializer_class(instance, fields=changes, excluded_fields=('links', 'channel', 'channel_room')).data

    channel.create_change(room=room,
                          author=author,
                          metadata=metadata,
                          payload=payload,
                          action=action)


@receiver(post_tenant_migrate, dispatch_uid='create_default_channels_after_tenant_migrate')
def create_default_channels_after_tenant_migrate(sender, tenant, created, partial, **kwargs):
    if not created:
        return

    # Default channel
    channel_props = {
        'type': Channel.TYPES.SEPARATE_ROOMS,
        'custom_publish': True,
        'acl': {'*': Channel.get_acl_permission_values()},
    }

    if partial:
        Channel.objects.get_or_create(name=Channel.DEFAULT_NAME, defaults=channel_props)
    else:
        Channel.objects.create(name=Channel.DEFAULT_NAME, **channel_props)

    # Eventlog channel
    channel_props = {
        'type': Channel.TYPES.SEPARATE_ROOMS,
        'custom_publish': False,
        'acl': {},
    }

    if partial:
        Channel.objects.get_or_create(name=Channel.EVENTLOG_NAME, defaults=channel_props)
    else:
        Channel.objects.create(name=Channel.EVENTLOG_NAME, **channel_props)
