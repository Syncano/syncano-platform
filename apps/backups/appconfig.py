from django.apps import AppConfig as _AppConfig


class AppConfig(_AppConfig):
    name = 'apps.backups'

    def ready(self):
        from . import signal_handlers  # noqa
        self.module.autodiscover()
