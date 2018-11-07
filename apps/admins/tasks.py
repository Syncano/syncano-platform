# coding=UTF8
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from settings.celeryconf import app, register_task

from apps.admins.models import Admin
from apps.core.mixins import TaskLockMixin


@register_task
class RemoveBotAccounts(app.Task):
    def run(self, **kwargs):
        purge_time = timezone.now() - timedelta(hours=1)

        for admin in Admin.objects.filter(email__regex=settings.BOT_EMAIL_RE, created_at__lte=purge_time):
            admin.delete()


@register_task
class DeleteInactiveAccounts(TaskLockMixin, app.Task):
    chunk_size = 25

    def run(self, last_pk=None):
        prune_time = timezone.now() - timedelta(days=settings.ACCOUNT_NOTICE_CONFIRMATION_DAYS)
        admins = Admin.objects.filter(noticed_at__lt=prune_time).exclude(subscriptions__plan__paid_plan=True)
        if last_pk is not None:
            admins.filter(pk__gt=last_pk)

        admins = list(admins[:self.chunk_size + 1])
        for admin in admins[:self.chunk_size]:
            admin.delete()

        if len(admins) > self.chunk_size:
            self.delay(last_pk=admins[-1].pk)
