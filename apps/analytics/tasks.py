# coding=UTF8
from datetime import timedelta

import analytics
import lazy_object_proxy
from django.conf import settings
from django.db.models import Count
from django.utils import timezone
from settings.celeryconf import app, register_task

from apps.admins.models import Admin
from apps.analytics.client import Client
from apps.billing.models import Invoice, Profile, Subscription, Transaction
from apps.core.mixins import TaskLockMixin
from apps.invitations.models import Invitation

from .mixins import NotifyAboutPaymentMixin, NotifyAdminMixin, NotifyLimitReachedMixin, NotifyTimestampMixin

analytics.write_key = settings.ANALYTICS_WRITE_KEY
analytics.send = settings.ANALYTICS_ENABLED and len(settings.ANALYTICS_WRITE_KEY) > 0
analytics.default_client = lazy_object_proxy.Proxy(lambda: Client(analytics.write_key,
                                                                  send=analytics.send, debug=analytics.debug))
TRANSACTION_SOURCE_DICT = {Transaction.SOURCES.API_CALL: 'API',
                           Transaction.SOURCES.CODEBOX_TIME: 'CodeBox'}


class NotifyBaseTask(app.Task):
    default_retry_delay = 60 * 5

    def after_return(self, *args, **kwargs):
        if analytics.send:
            analytics.flush()


class NotifyLockBaseTask(TaskLockMixin, NotifyBaseTask):
    lock_generate_hash = True


@register_task
class NotifyAboutAdminSignup(NotifyAdminMixin, NotifyTimestampMixin, NotifyBaseTask):
    def run(self, admin_id, email, created_at, distinct_id=None, backend='password', activation_url=None):
        if distinct_id is not None:
            analytics.alias(distinct_id, email)
        analytics.alias(email, admin_id)

        analytics.identify(admin_id, traits={'email': email, 'Lifecycle stage': 'customer', 'created_at': created_at},
                           timestamp=self.timestamp)
        data = {'authBackend': backend}
        if activation_url is not None:
            data['activationUrl'] = activation_url
        analytics.track(admin_id, 'Sign up', data, timestamp=self.timestamp)


@register_task
class NotifyAboutResendAdminActivationEmail(NotifyAdminMixin, NotifyTimestampMixin, NotifyBaseTask):
    def run(self, admin_id, uid, token):
        activation_url = settings.GUI_ACTIVATION_URL % {'uid': uid, 'token': token}
        analytics.track(admin_id, 'Activation resend', {
            'activationUrl': activation_url,
            'authBackend': 'password'
        }, timestamp=self.timestamp)


@register_task
class NotifyAboutAdminActivation(NotifyAdminMixin, NotifyTimestampMixin, NotifyBaseTask):
    def run(self, admin_id, uid, email, token):
        activation_url = settings.GUI_ACTIVATION_URL % {'uid': uid, 'token': token}
        analytics.track(admin_id, 'Sign Up Activation', {'activationUrl': activation_url, 'authBackend': 'password'},
                        timestamp=self.timestamp)
        analytics.identify(
            admin_id,
            traits={'email': email, 'activationUrl': activation_url},
            context={'active': False},
            timestamp=self.timestamp
        )


@register_task
class NotifyAboutAdminPasswordReset(NotifyAdminMixin, NotifyTimestampMixin, NotifyBaseTask):
    def run(self, admin_id, uid, token):
        url = settings.GUI_CONFIRM_RESET_PASSWORD_URL % {'uid': uid, 'token': token}
        analytics.track(admin_id, 'Password reset', {
            'uid': uid,
            'token': token,
            'passwordResetUrl': url,
        }, timestamp=self.timestamp)


@register_task
class NotifyAboutLogIn(NotifyAdminMixin, NotifyTimestampMixin, NotifyBaseTask):
    def run(self, admin_id, email, auth_backend):
        analytics.track(admin_id, 'Sign in', {
            'email': email,
            'authBackend': auth_backend
        }, timestamp=self.timestamp)


@register_task
class NotifyAboutLogInFailure(NotifyAdminMixin, NotifyTimestampMixin, NotifyBaseTask):
    def run(self, admin_id, email, auth_backend):
        analytics.track(admin_id, 'Sign in failure', {
            'email': email,
            'authBackend': auth_backend
        }, timestamp=self.timestamp)


@register_task
class NotifyAboutInvitation(NotifyTimestampMixin, NotifyBaseTask):
    """
    Notifies a segment.io about the new invitation, what causes sending an email with invitation.

    If a person who doesn't have an account yet receives an invitation, we identify new potential customer
    in segment.io.
    """

    def run(self, invitation_id):
        logger = self.get_logger()

        try:
            invitation = Invitation.objects.select_related('inviter').get(id=invitation_id)
        except Invitation.DoesNotExist:
            logger.warning('Cannot notify segment.io about Invitation[id=%d] because it cannot be found.',
                           invitation_id)
            return
        logger.info('Notify segment.io about %s.', invitation)

        email = invitation.email
        if invitation.admin_id is None:
            analytics.identify(email,
                               traits={'email': email, 'Lifecycle stage': 'lead',
                                       'source': 'Invitation'},
                               context={'active': False},
                               timestamp=self.timestamp)

        invitation_url = settings.INVITATION_SITE_URL + '?invitation_key=%s' % invitation.key

        # if invitation was created by admin, we will include it in invitation event
        if invitation.inviter is None:
            inviter = None
        else:
            inviter = invitation.inviter.email

        analytics.track(invitation.admin_id or email, 'Invitation received',
                        {
                            'invitationUrl': invitation_url,
                            'inviter': inviter,
                            'instance': invitation.instance.name
                        },
                        timestamp=self.timestamp)


@register_task
class NotifyAboutSoftLimitReached(NotifyLimitReachedMixin, NotifyTimestampMixin, NotifyBaseTask):
    def run(self, admin_id):
        profile = Profile.objects.select_related('admin').get(admin_id=admin_id)
        analytics.track(admin_id, 'Soft limit reached', {
            'softLimit': profile.soft_limit_formatted,
            'plan': profile.current_subscription.plan.name,
            'period': profile.soft_limit_reached.strftime(settings.ANALYTICS_DATE_FORMAT)
        }, timestamp=self.timestamp)


@register_task
class NotifyAboutHardLimitReached(NotifyLimitReachedMixin, NotifyTimestampMixin, NotifyBaseTask):
    def run(self, admin_id):
        profile = Profile.objects.select_related('admin').get(admin_id=admin_id)
        analytics.track(admin_id, 'Hard limit reached', {
            'hardLimit': profile.hard_limit_formatted,
            'plan': profile.current_subscription.plan.name,
            'period': profile.hard_limit_reached.strftime(settings.ANALYTICS_DATE_FORMAT)
        }, timestamp=self.timestamp)


@register_task
class NotifyAboutPaymentReceived(NotifyAboutPaymentMixin, NotifyTimestampMixin, NotifyLockBaseTask):
    def run(self, reference, payment_date):
        qs = Invoice.objects.select_related('admin__billing_profile')
        invoice = qs.get(reference=reference, status=Invoice.STATUS_CHOICES.PAYMENT_SUCCEEDED)
        period_start = invoice.created_at.date() if invoice.is_prorated else invoice.period_start
        period_end = invoice.period_end
        profile = invoice.admin.billing_profile
        billing_field_names = ('company_name', 'first_name', 'last_name', 'address_line1', 'address_line2',
                               'address_city', 'address_state', 'address_zip', 'address_country',
                               'tax_number')
        billing_profile_data = {field_name: getattr(profile, field_name) for field_name in billing_field_names}
        analytics.track(invoice.admin.id, 'Payment processed', {
            'amount': invoice.formatted_amount,
            'revenue': float(invoice.rounded_amount),
            'receiptUrl': settings.GUI_BILLING_HISTORY_URL,
            'paymentDate': payment_date,
            'isInvoiceForOverage': invoice.is_invoice_for_overage,
            'isProrated': invoice.is_prorated,
            'billingData': billing_profile_data,
            # If we're prorated, use creation date as period start
            'periodBegin': period_start.strftime(settings.ANALYTICS_DATE_FORMAT),
            'periodEnd': period_end.strftime(settings.ANALYTICS_DATE_FORMAT),
        }, timestamp=self.timestamp)


@register_task
class NotifyAboutPaymentFailure(NotifyAboutPaymentMixin, NotifyTimestampMixin, NotifyLockBaseTask):
    def run(self, reference):
        qs = Invoice.objects.select_related('admin')
        invoice = qs.get(reference=reference, status=Invoice.STATUS_CHOICES.PAYMENT_FAILED)
        analytics.track(invoice.admin.id, 'Payment failure', timestamp=self.timestamp)


class NotifyAboutUsage(NotifyTimestampMixin, NotifyBaseTask):
    source = None
    value_label = None

    def run(self, admin_id, instance_name, value):
        analytics.track(admin_id, self.source,
                        {'instance': instance_name, self.value_label: value},
                        timestamp=self.timestamp)


@register_task
class NotifyAboutApiCalls(NotifyAboutUsage):
    source = 'API Calls'
    value_label = 'apiCalls'


@register_task
class NotifyAboutCodeBoxSeconds(NotifyAboutUsage):
    source = 'CodeBox Runs'
    value_label = 'codeboxSeconds'


@register_task
class NotifyAboutApiAndCodeBoxSeconds(NotifyTimestampMixin, NotifyBaseTask):
    source = 'API or CodeBox'
    api_label = NotifyAboutApiCalls.value_label
    codebox_label = NotifyAboutCodeBoxSeconds.value_label

    def run(self, admin_id, instance_name, api_calls=None, codebox_runs=None):
        event_props = {'instance': instance_name}
        if api_calls is not None:
            event_props[self.api_label] = api_calls
        if codebox_runs is not None:
            event_props[self.codebox_label] = codebox_runs

        analytics.track(admin_id, self.source,
                        event_props,
                        timestamp=self.timestamp)


@register_task
class AdminStateUpdater(NotifyLockBaseTask):
    chunk_size = 1000
    lock_generate_hash = False

    def run(self, last_pk=None):
        logger = self.get_logger()
        chunk_size = self.chunk_size

        admins = Admin.objects.annotate(instance_count=Count('own_instances')).values_list(
            'pk', 'email', 'instance_count', 'first_name', 'last_name'
        )
        if last_pk is not None:
            admins = admins.filter(pk__gt=last_pk)
        admins_list = list(admins[:chunk_size])
        now = timezone.now()

        for pk, email, instance_count, first_name, last_name in admins_list:
            analytics.identify(pk, traits={'email': email, 'numberOfInstances': instance_count,
                                           'firstName': first_name, 'lastName': last_name},
                               context={'active': False}, timestamp=now)

        if len(admins_list) == chunk_size:
            logger.info('Scheduling task with next chunk of admins.')
            self.delay(last_pk=admins_list[-1][0])


@register_task
class NotifyAboutPlanUsage(NotifyTimestampMixin, NotifyBaseTask):
    default_retry_delay = 60 * 5

    def run(self, admin_id, plan, usage, source):
        analytics.track(admin_id, '%s Limit' % TRANSACTION_SOURCE_DICT[source],
                        {'plan': plan,
                         'used': usage,
                         'used%': usage / plan},
                        timestamp=self.timestamp)


@register_task
class NotifyAboutPlanChange(NotifyTimestampMixin, NotifyBaseTask):
    default_retry_delay = 60 * 5

    def run(self, subscription_pk):
        try:
            subscription = Subscription.objects.select_related('plan').get(pk=subscription_pk)
        except Subscription.DoesNotExist:
            self.get_logger().warning('Cannot notify segment.io about Subscription[id=%d] because it cannot be found.',
                                      subscription_pk)
            return
        cbx_plan, api_plan, total_plan = self._get_plan_options(subscription)

        analytics.track(subscription.admin.id, 'Billing plan changed',
                        {'Plan': subscription.plan.name,
                         'CodeBox Plan {cbx_plan}'.format(cbx_plan=cbx_plan): cbx_plan,
                         'API Plan {api_plan}'.format(api_plan=api_plan): api_plan,
                         'Total Plan {total_plan}'.format(total_plan=total_plan): total_plan,
                         'Start Date': subscription.start},
                        timestamp=self.timestamp)

    @staticmethod
    def _get_plan_options(subscription):
        commitment = subscription.commitment
        cbx_plan = int(commitment.get('cbx', 0))
        api_plan = int(commitment.get('api', 0))
        total_plan = cbx_plan + api_plan

        return cbx_plan, api_plan, total_plan


@register_task
class MonthlySummaryTask(NotifyTimestampMixin, NotifyLockBaseTask):
    chunk_size = 1000
    default_retry_delay = 60 * 5

    def run(self):
        invoices = Invoice.objects.filter(status_sent=False,
                                          period__lt=Invoice.current_period())
        invoices = invoices.select_related('admin').prefetch_related('items')
        invoices = invoices.order_by('pk')

        chunk = list(invoices[:self.chunk_size + 1])
        if not chunk:
            return

        try:
            for invoice in chunk[:self.chunk_size]:
                # Don't send summary for invoices without items with API_CALL or
                # CODEBOX_TIME. Because we prefetched items we check this in python
                if any(item for item in invoice.items.all() if not item.is_fee()):
                    analytics.track(
                        invoice.admin.id,
                        'Monthly Summary',
                        {
                            'apiCalls': invoice.get_usage(Transaction.SOURCES.API_CALL),
                            'codeboxSeconds': invoice.get_usage(
                                Transaction.SOURCES.CODEBOX_TIME),
                            'apiPlan': invoice.get_display_plan_limit(
                                Transaction.SOURCES.API_CALL),
                            'codeboxPlan': invoice.get_display_plan_limit(
                                Transaction.SOURCES.CODEBOX_TIME)
                        },
                        timestamp=self.timestamp)
        finally:
            invoices.filter(pk__lte=chunk[-1].pk).update(status_sent=True)

        if len(chunk) > self.chunk_size:
            self.delay()


@register_task
class SendUnusedAccountNotification(NotifyLockBaseTask):
    chunk_size = 100
    default_retry_delay = 60 * 5

    def run(self):
        last_access_limit = timezone.now() - timedelta(days=settings.ACCOUNT_MAX_IDLE_DAYS)
        admins = Admin.objects.filter(last_access__lte=last_access_limit,
                                      noticed_at__isnull=True,
                                      is_staff=False).exclude(subscriptions__plan__paid_plan=True)

        now = timezone.now()

        admins_list = admins[:self.chunk_size + 1]
        for admin in admins_list[:self.chunk_size]:
            data = {'accountEmail': admin.email,
                    'lastAccess': admin.last_access,
                    'allowedInactivityDays': settings.ACCOUNT_MAX_IDLE_DAYS,
                    'confirmationDays': settings.ACCOUNT_NOTICE_CONFIRMATION_DAYS,
                    'link': settings.GUI_PROLONG_URL}
            analytics.track(admin.id, 'Account deletion warning',
                            data, timestamp=now)

        Admin.objects.filter(pk__in=[admin.pk for admin in admins_list]).update(noticed_at=now)
        if len(admins_list) > self.chunk_size:
            self.get_logger().info('Scheduling task with next chunk of admins.')
            self.delay()
