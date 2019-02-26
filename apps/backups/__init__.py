from django.utils.module_loading import autodiscover_modules

from apps.backups.site import default_site

default_app_config = 'apps.backups.appconfig.AppConfig'


def autodiscover():
    """Import backup.py module for each of INSTALLED_APPS"""
    autodiscover_modules('backup', register_to=default_site)
