# coding=UTF8
import analytics
from celery.signals import worker_shutdown
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.analytics.tasks import NotifyAboutPlanChange
from apps.billing.models import Subscription
from apps.core.decorators import disable_during_tests
from apps.core.helpers import add_post_transaction_success_operation


@worker_shutdown.connect
def worker_shutdown_handler(**kwargs):
    if analytics.send:
        analytics.flush()


@receiver(post_save, sender=Subscription, dispatch_uid='notify_about_pricing_plan_change')
@disable_during_tests
def notify_about_pricing_plan_change(sender, instance, created, **kwargs):
    add_post_transaction_success_operation(NotifyAboutPlanChange.delay, subscription_pk=instance.pk)
