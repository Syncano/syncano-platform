# coding=UTF8
from settings.celeryconf import *  # noqa
from settings.common import LOGGING

# Logging override
LOGGING['loggers']['celery_tasks']['level'] = 'DEBUG'
LOGGING['loggers']['django']['level'] = 'DEBUG'
