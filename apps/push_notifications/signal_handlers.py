from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.decorators import disable_during_tests
from apps.core.signals import post_tenant_migrate
from apps.instances.helpers import get_current_instance
from apps.instances.models import InstanceIndicator
from apps.push_notifications.models import APNSConfig, APNSDevice, APNSMessage, GCMConfig, GCMMessage
from apps.push_notifications.tasks import SendAPNSMessage, SendGCMMessage


@receiver(post_tenant_migrate, dispatch_uid='create_config_after_tenant_migrate')
@disable_during_tests
def create_config_after_tenant_migrate(sender, tenant, created, partial, **kwargs):
    if not created:
        return

    if partial:
        gcm_create = GCMConfig.objects.get_or_create
        apns_create = APNSConfig.objects.get_or_create
    else:
        gcm_create = GCMConfig.objects.create
        apns_create = APNSConfig.objects.create
    gcm_create(pk=1)
    apns_create(pk=1)


@receiver(post_save, sender=GCMMessage, dispatch_uid='delay_task_for_gcmmessage')
@disable_during_tests
def delay_task_for_gcmmessage(sender, instance, created, **kwargs):
    if created:
        SendGCMMessage.delay(instance.pk, instance_pk=get_current_instance().pk)


@receiver(post_save, sender=APNSMessage, dispatch_uid='delay_task_for_apnsmessage')
@disable_during_tests
def delay_task_for_apnsmessage(sender, instance, created, **kwargs):
    if created:
        SendAPNSMessage.delay(instance.pk, instance_pk=get_current_instance().pk)


def update_instance_apns_devices_indicator(change):
    instance = get_current_instance()
    indicator_type = InstanceIndicator.TYPES.APNS_DEVICES_COUNT
    q = InstanceIndicator.objects.filter(instance=instance, type=indicator_type)
    q.update(value=F('value') + change)


@receiver(post_save, sender=APNSDevice, dispatch_uid='apns_devices_post_save_handler')
def apns_devices_post_save(sender, instance, created, **kwargs):
    if created:
        update_instance_apns_devices_indicator(1)
    elif instance.has_changed('is_active'):
        if instance.is_active:
            update_instance_apns_devices_indicator(1)
        else:
            update_instance_apns_devices_indicator(-1)


@receiver(post_delete, sender=APNSDevice, dispatch_uid='apns_devices_post_delete_handler')
def apns_devices_post_delete_handler(sender, instance, **kwargs):
    if instance.is_active:
        update_instance_apns_devices_indicator(-1)
