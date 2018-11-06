# coding=UTF8
import os

from celery import Celery
from celery.concurrency import asynpool
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.development")

asynpool.PROC_ALIVE_TIMEOUT = settings.CELERY_PROC_ALIVE_TIMEOUT
app = Celery('syncano', task_cls='apps.core.tasks:BaseTask')

CELERY_TIMEZONE = 'UTC'

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


def register_task(cls):
    return app.register_task(cls())
