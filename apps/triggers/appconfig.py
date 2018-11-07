# coding=UTF8
from django.apps import AppConfig as _AppConfig


class AppConfig(_AppConfig):
    name = 'apps.triggers'

    def ready(self):
        from . import signal_handlers  # noqa
