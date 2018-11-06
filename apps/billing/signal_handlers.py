import logging
from datetime import timedelta

from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from psycopg2.extras import DateRange

from apps.admins.models import Admin
from apps.analytics.tasks import NotifyAboutPaymentFailure, NotifyAboutPaymentReceived
from apps.billing.exceptions import StorageLimitReached
from apps.core.helpers import add_post_transaction_success_operation
from apps.instances.helpers import get_current_instance
from apps.instances.models import InstanceIndicator
from apps.metrics.signals import interval_aggregated
from apps.metrics.tasks import AggregateHourTask

from .models import AdminLimit, Invoice, PricingPlan, Profile, Subscription
from .signals import EVENT_SIGNALS
from .tasks import ChargeOneHour, create_stripe_customer, remove_stripe_customer

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Admin, dispatch_uid='create_subscription_for_new_admin')
def create_subscription_for_new_admin(sender, instance, created, **kwargs):
    if created:
        admin = instance
        start = admin.created_at.date()
        end = None
        if admin.is_staff or admin.is_superuser:
            plan = PricingPlan.objects.get(name='free')
        else:
            plan = PricingPlan.objects.get_default()
            if settings.BILLING_DEFAULT_PLAN_TIMEOUT > 0:
                end = start + timedelta(days=settings.BILLING_DEFAULT_PLAN_TIMEOUT)
        Subscription.objects.create(plan=plan, admin=admin, range=DateRange(start, end))


@receiver(interval_aggregated, sender=AggregateHourTask, dispatch_uid='charge_after_metrics_process_interval')
def charge_after_metrics_process_interval(sender, left_boundary, right_boundary, **kwargs):
    ChargeOneHour.delay(left_boundary.isoformat())


@receiver(post_save, sender=Admin, dispatch_uid='create_models_for_admin')
def create_models_for_admin(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(admin=instance)
        AdminLimit.objects.create(admin=instance)


@receiver(post_save, sender=Profile, dispatch_uid='create_stripe_customer')
def create_stripe_customer_handler(sender, instance, created, **kwargs):
    if created and not instance.customer_id:
        add_post_transaction_success_operation(
            create_stripe_customer.delay,
            instance.pk,
            email=instance.admin.email
        )


@receiver(post_delete, sender=Profile, dispatch_uid='remove_stripe_customer')
def remove_stripe_customer_handler(sender, instance, **kwargs):
    if instance.customer_id:
        add_post_transaction_success_operation(
            remove_stripe_customer.delay,
            instance.admin_id,
            instance.customer_id
        )


def process_charge(event, invoice_status, required=True):
    reference = event.message['data']['object']['metadata']['reference']
    qs = Invoice.objects.filter(reference=reference)
    qs = qs.exclude(status=Invoice.STATUS_CHOICES.PAYMENT_SUCCEEDED)
    affected = qs.update(status=invoice_status)
    if not affected:
        if required:
            logger.error('Invalid invoice event: %s', event.pk)
        return reference, False
    return reference, True


@receiver(EVENT_SIGNALS['charge.succeeded'], dispatch_uid='stripe_charge_succeeded')
@receiver(EVENT_SIGNALS['charge.captured'], dispatch_uid='stripe_charge_captured')
def charge_succeeded(event, **kwargs):
    reference, processed = process_charge(event, Invoice.STATUS_CHOICES.PAYMENT_SUCCEEDED)
    if processed:
        add_post_transaction_success_operation(
            NotifyAboutPaymentReceived.delay,
            reference,
            event.created_at.strftime(settings.ANALYTICS_DATE_FORMAT))


@receiver(EVENT_SIGNALS['charge.failed'], dispatch_uid='stripe_charge_failed')
def charge_failed(event, **kwargs):
    # Invoice is not required for payment failed as it may not be existing anymore (e.g. when it was a temporary
    # invoice created during creation of subscription)
    reference, processed = process_charge(event, Invoice.STATUS_CHOICES.PAYMENT_FAILED, required=False)
    if processed:
        add_post_transaction_success_operation(NotifyAboutPaymentFailure.delay, reference)


# Enforce builder storage limit
@receiver(post_save, sender=InstanceIndicator, dispatch_uid='indicator_post_save_handler')
def indicator_post_save_handler(sender, instance, created, **kwargs):
    tenant = get_current_instance() or instance.instance

    if not created and instance.type == InstanceIndicator.TYPES.STORAGE_SIZE:
        storage_limit = AdminLimit.get_for_admin(tenant.owner_id).get_storage()
        if instance.value > instance.old_value('value') and instance.value > storage_limit >= 0:
            raise StorageLimitReached()
