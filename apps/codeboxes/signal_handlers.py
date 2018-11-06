# coding=UTF8
import os

from celery.signals import worker_process_init, worker_process_shutdown
from django.db.models import F
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.codeboxes.container_manager import ContainerManager
from apps.codeboxes.models import CodeBoxSchedule
from apps.instances.helpers import get_current_instance
from apps.instances.models import InstanceIndicator


def update_instance_schedule_indicator(change):
    instance = get_current_instance()
    indicator_type = InstanceIndicator.TYPES.SCHEDULES_COUNT
    q = InstanceIndicator.objects.filter(instance=instance, type=indicator_type)
    q.update(value=F('value') + change)


@receiver(post_save, sender=CodeBoxSchedule, dispatch_uid='schedule_post_save_handler')
def schedule_post_save(sender, instance, created, **kwargs):
    if created:
        update_instance_schedule_indicator(1)


@receiver(post_delete, sender=CodeBoxSchedule, dispatch_uid='schedule_post_delete_handler')
def schedule_post_delete_handler(sender, instance, **kwargs):
    update_instance_schedule_indicator(-1)


@worker_process_init.connect
def configure_workers_prep(*args, **kwargs):
    if os.environ.get('INSTANCE_TYPE') == 'codebox':
        ContainerManager.prepare_all_containers()


@worker_process_shutdown.connect
def configure_workers_shut(*args, **kwargs):
    if os.environ.get('INSTANCE_TYPE') == 'codebox':
        ContainerManager.dispose_all_containers()
