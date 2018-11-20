# coding=UTF8
from settings.common import *  # noqa

# Quick settings
CACHE = True
ZIPKIN_RAISE = True

MIDDLEWARE = ('apps.core.middleware.InstrumentMiddleware',) + MIDDLEWARE

REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] += ('rest_framework.renderers.BrowsableAPIRenderer',)

# Cache
if not CACHE:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        }
    }


# Logging override
LOGGING['loggers']['celery.redirected']['level'] = 'WARNING'
