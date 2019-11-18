# coding=UTF8
import os
from datetime import timedelta

from celery.schedules import crontab
from django.utils.dateparse import parse_date
from kombu import Exchange, Queue

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

SECRET_KEY = os.environ.get('SECRET_KEY', 'secret_key')

# used for load testing on loader.io
LOADERIO_TOKEN = os.environ.get('LOADERIO_TOKEN', '')

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
GDAL_LIBRARY_PATH = os.environ.get('GDAL_LIBRARY_PATH')
GEOS_LIBRARY_PATH = os.environ.get('GEOS_LIBRARY_PATH')

TESTING = False
CI = False
DEBUG = os.environ.get('DJANGO_DEBUG', 'false') == 'true'

# Application definition
LOCATION = os.environ.get('LOCATION', 'stg')
LOCATIONS = os.environ.get('LOCATIONS', LOCATION).split(',')
MAIN_LOCATION = LOCATIONS[0] == LOCATION
SITE_ID = 1
ALLOWED_HOSTS = ('*',)
REGISTRATION_ENABLED = os.environ.get('REGISTRATION_ENABLED', 'true') == 'true'

AUTH_USER_MODEL = 'admins.Admin'
TENANT_MODEL = 'instances.Instance'
DATABASE_ROUTERS = (
    'apps.instances.routers.InstanceRouter',
)

API_DOMAIN = os.environ.get('API_DOMAIN', 'api.syncano.io')
API_LOCATION_DOMAIN = os.environ.get('API_LOCATION_DOMAIN', 'api-{location}.syncano.io')
SPACE_DOMAIN = os.environ.get('SPACE_DOMAIN', 'syncano.space')


SHARED_APPS = (
    'django.contrib.sites',
    'django.contrib.staticfiles',
    'django.contrib.gis',

    # We do not use these two, but they are required (when imported) as of Django 1.9 as it otherwise raises an error
    'django.contrib.auth',
    'django.contrib.contenttypes',

    'raven',
    'raven.contrib.django.raven_compat',
    'rest_framework',
    'corsheaders',
    'django_atomic_signals',
    'django_extensions',

    'apps.core',
    'apps.apikeys',
    'apps.instances',
    'apps.invitations',
    'apps.admins',
    'apps.metrics',
    'apps.billing',
    'apps.async_tasks',
    'apps.analytics',
    'apps.batch',
    'apps.controlpanel',
    'apps.backups',
    'apps.redis_storage',
)

TENANT_APPS = (
    'apps.data',
    'apps.users',
    'apps.codeboxes',
    'apps.triggers',
    'apps.webhooks',
    'apps.channels',
    'apps.high_level',
    'apps.push_notifications',
    'apps.response_templates',
    'apps.endpoints',
    'apps.snippets',
    'apps.hosting',
    'apps.sockets',
)

TEST_NON_SERIALIZED_APPS = TENANT_APPS
INSTALLED_APPS = SHARED_APPS + TENANT_APPS

# REST framework
DATE_FORMAT = '%Y-%m-%d'
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
ANALYTICS_DATE_FORMAT = '%b %d %Y'

ANON_THROTTLE_RATE = os.environ.get('ANON_THROTTLE_RATE', '10')
USER_THROTTLE_RATE = os.environ.get('USER_THROTTLE_RATE', '60')
INSTANCE_THROTTLE_RATE = os.environ.get('INSTANCE_THROTTLE_RATE', '60')

MAX_PAGE_SIZE = 100
MAX_RESPONSE_SIZE = 2 * 1024 * 1024
RESPONSE_ENCODED = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.core.authentication.ApiKeyAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'apps.admins.permissions.AdminHasPermissions',
        'apps.billing.permissions.OwnerInGoodStanding',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'apps.core.renderers.JSONRenderer',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'apps.core.parsers.JSONParser',
        'apps.batch.parsers.PreflightParser',
        'apps.core.parsers.FormParser',
        'apps.core.parsers.MultiPartParser'
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'apps.core.throttling.AnonRateThrottle',
        'apps.core.throttling.AdminRateThrottle',
        'apps.core.throttling.ScopedRateThrottle',
        'apps.instances.throttling.InstanceRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '%s/second' % ANON_THROTTLE_RATE,
        'user': '%s/second' % USER_THROTTLE_RATE,
        'invoice_retry_payment': '3/minute',
        'zip_file': '3/minute',
    },
    'DEFAULT_CONTENT_NEGOTIATION_CLASS': 'apps.response_templates.negotiations.ResponseTemplateNegotiation',
    'DEFAULT_METADATA_CLASS': 'apps.core.metadata.Metadata',
    'DEFAULT_FILTER_BACKENDS': [],
    'DATE_FORMAT': DATE_FORMAT,
    'DATETIME_FORMAT': DATETIME_FORMAT,
    'DATETIME_INPUT_FORMATS': [DATETIME_FORMAT],
    'TEST_REQUEST_DEFAULT_FORMAT': 'json',
    'EXCEPTION_HANDLER': 'apps.core.views.exception_handler',
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.StandardPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_VERSIONING_CLASS': 'apps.core.versioning.NamespaceVersioning',
    'DEFAULT_VERSION': 'v1',
    'ALLOWED_VERSIONS': ['v1', 'v1.1', 'v2'],
}

# Database
ORIGINAL_BACKEND = 'django.contrib.gis.db.backends.postgis'
DATABASES = {
    'default': {
        'ENGINE': 'apps.instances.postgresql_backend',
        'NAME': os.environ.get('DB_NAME', 'syncano'),
        'USER': os.environ.get('DB_USER', 'syncano'),
        'PASSWORD': os.environ.get('DB_PASS', 'syncano'),
        'HOST': os.environ.get('DB_ADDR', 'postgresql'),
        'PORT': '',
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', 0))
    },
    'instances': {
        'ENGINE': 'apps.instances.postgresql_backend',
        # We should ignore empty string as env var so it works fine with docker-compose
        'NAME': os.environ.get('DB_INSTANCES_NAME', os.environ.get('DB_NAME', 'syncano')),
        'USER': os.environ.get('DB_INSTANCES_USER', os.environ.get('DB_USER', 'syncano')),
        'PASSWORD': os.environ.get('DB_INSTANCES_PASS', os.environ.get('DB_PASS', 'syncano')),
        'HOST': os.environ.get('DB_INSTANCES_ADDR', os.environ.get('DB_ADDR', 'postgresql')),
        'PORT': '',
        'TEST': {'SERIALIZE': False},
        'CONN_MAX_AGE': int(os.environ.get('DB_INSTANCES_CONN_MAX_AGE',
                                           os.environ.get('DB_CONN_MAX_AGE', 0))),
    },
}

# Redis
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_HOST = os.environ.get('REDIS_ADDR', 'redis')


# Cache
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://{}:{}/{}'.format(REDIS_HOST, REDIS_PORT, REDIS_DB),
        'KEY_FUNCTION': 'apps.core.backends.make_cache_key',
        'OPTIONS': {
            'PICKLE_VERSION': -1,  # default
            'PARSER_CLASS': 'redis.connection.HiredisParser',
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    },
}
CACHE_VERSION = int(os.environ.get('CACHE_VERSION', 1))
CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 24 * 60 * 60))  # 24 hours
LOCAL_CACHE_TIMEOUT = int(os.environ.get('LOCAL_CACHE_TIMEOUT', 1 * 60 * 60))  # 1 hour
LOCK_TIMEOUT = int(os.environ.get('LOCK_TIMEOUT', 15))

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

MIDDLEWARE = (
    'apps.core.middleware.PrepareRequestMiddleware',
    'apps.core.middleware.ZipkinMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'apps.hosting.middleware.HostingMiddleware',
)

# URLs
ROOT_URLCONF = 'urls.backend'
APPEND_SLASH = False

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static/')

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')

# S3 - django-storages settings
STORAGE_TYPE = os.environ.get('STORAGE_TYPE', 'local')
AWS_IS_GZIPPED = False
AWS_S3_FILE_OVERWRITE = False
AWS_S3_SECURE_URLS = True  # use https
AWS_QUERYSTRING_AUTH = False  # don't add complex authentication-related query parameters for requests
AWS_S3_CUSTOM_DOMAIN = os.environ.get('S3_CUSTOM_DOMAIN', '')  # e.g. d1e3fhjr88e1hl.cloudfront.net
AWS_DEFAULT_ACL = 'public-read'
GS_DEFAULT_ACL = 'publicRead'

S3_ACCESS_KEY_ID = os.environ.get('S3_ACCESS_KEY_ID', '')
S3_SECRET_ACCESS_KEY = os.environ.get('S3_SECRET_ACCESS_KEY', '')
S3_REGION = os.environ.get('S3_REGION')
S3_ENDPOINT = os.environ.get('S3_ENDPOINT')

STORAGE_HOSTING_BUCKET = os.environ.get('STORAGE_HOSTING_BUCKET', '')
STORAGE_BUCKET = os.environ.get('STORAGE_BUCKET', '')

LOCAL_MEDIA_STORAGE = STORAGE_TYPE == 'local'

DEFAULT_FILE_STORAGE = 'apps.core.backends.storage.DefaultStorage'

# Celery settings
CELERY_BROKER_URL = os.environ.get('BROKER_URL', '')
if not CELERY_BROKER_URL:
    RABBIT_HOSTNAME = os.environ.get('RABBITMQ_ADDR', 'rabbitmq')
    if RABBIT_HOSTNAME.startswith('tcp://'):
        RABBIT_HOSTNAME = RABBIT_HOSTNAME.split('//')[1]
    CELERY_BROKER_URL = 'amqp://{user}:{password}@{hostname}/{vhost}'.format(
        user=os.environ.get('RABBIT_ENV_USER', 'guest'),
        password=os.environ.get('RABBIT_ENV_RABBITMQ_PASS', 'guest'),
        hostname=RABBIT_HOSTNAME,
        vhost=os.environ.get('RABBIT_ENV_VHOST', '/'))


CELERY_RESULT_BACKEND = os.environ.get('RESULT_BACKEND', 'redis://%s:%d/%d' % (REDIS_HOST, REDIS_PORT, REDIS_DB))
CELERY_TASK_PROTOCOL = 1
CELERY_BROKER_POOL_LIMIT = 2
CELERY_BROKER_TRANSPORT_OPTIONS = {'confirm_publish': True}
CELERY_TASK_SERIALIZER = os.environ.get('CELERY_FORMAT', 'json')
CELERY_RESULT_SERIALIZER = CELERY_TASK_SERIALIZER
CELERY_ACCEPT_CONTENT = {'json', 'pickle'}
CELERY_WORKER_DISABLE_RATE_LIMITS = True
CELERY_TASK_IGNORE_RESULT = True
CELERY_RESULT_EXPIRES = 600
CELERY_PROC_ALIVE_TIMEOUT = 60.0

CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

DEFAULT_QUEUE = 'default'
PERIODIC_SCHEDULERS_QUEUE = 'periodic_schedulers'
CODEBOX_QUEUE = 'codebox'
CODEBOX_RUNNER_QUEUE = 'codebox_runner'
METRICS_QUEUE = 'metrics'
PUSH_NOTIFICATIONS_QUEUE = 'push_notifications'
BACKUPS_QUEUE = 'backups'
ROOT_TASKS_QUEUE = 'root_tasks'

CELERY_TASK_DEFAULT_QUEUE = 'default'

CELERY_TASK_QUEUES = (
    Queue(DEFAULT_QUEUE, Exchange('default'), routing_key=DEFAULT_QUEUE),
    Queue(PERIODIC_SCHEDULERS_QUEUE, routing_key=PERIODIC_SCHEDULERS_QUEUE),
    Queue(CODEBOX_QUEUE, routing_key=CODEBOX_QUEUE),
    Queue(CODEBOX_RUNNER_QUEUE, routing_key=CODEBOX_RUNNER_QUEUE),
    Queue(METRICS_QUEUE, routing_key=METRICS_QUEUE),
    Queue(PUSH_NOTIFICATIONS_QUEUE, routing_key=PUSH_NOTIFICATIONS_QUEUE),
    Queue(BACKUPS_QUEUE, routing_key=BACKUPS_QUEUE),
    Queue(ROOT_TASKS_QUEUE, routing_key=ROOT_TASKS_QUEUE),
)

CELERY_BEAT_SCHEDULE = {
    'metrics-aggregate-minute-runner': {
        'task': 'apps.metrics.tasks.AggregateMinuteRunnerTask',
        'schedule': timedelta(seconds=60),
    },
    'codeboxes-scheduler': {
        'task': 'apps.codeboxes.tasks.SchedulerDispatcher',
        'schedule': timedelta(seconds=20)
    },
    'refresh-custom-domains-ssl-certificate': {
        'task': 'apps.hosting.tasks.HostingRefreshSecureCustomDomainCertTask',
        'schedule': crontab(hour=4)
    },
    'push-notifications-dispatcher': {
        'task': 'apps.push_notifications.tasks.APNSFeedbackDispatcher',
        'schedule': crontab(minute=30, hour=2)
    },
}

if MAIN_LOCATION:
    CELERY_BEAT_SCHEDULE.update({
        'billing-issue-invoices': {
            'task': 'apps.billing.tasks.InvoiceDispatcher',
            # We need to start invoicing after aggregation of transactions
            'schedule': crontab(minute=30, hour=1)
        },
        'billing-issue-planfee': {
            'task': 'apps.billing.tasks.PlanFeeDispatcher',
            'schedule': crontab(minute=0, hour=2)
        },
        'analytics-monthly-summary-notifications': {
            'task': 'apps.analytics.tasks.MonthlySummaryTask',
            # We need to start MonthlySummary notifications after processing Invoices
            'schedule': crontab(minute=30, hour=2)
        },
        'admin-state-update': {
            'task': 'apps.analytics.tasks.AdminStateUpdater',
            'schedule': crontab(minute=0, hour=0)
        },
        'unused-account-notification': {
            'task': 'apps.analytics.tasks.SendUnusedAccountNotification',
            'schedule': crontab(minute=0, hour=1)
        },
        'delete-inactive-accounts': {
            'task': 'apps.admins.tasks.DeleteInactiveAccounts',
            'schedule': crontab(minute=30, hour=1)
        },
        'remove-end-to-end-test-accounts': {
            'task': 'apps.admins.tasks.RemoveBotAccounts',
            'schedule': timedelta(hours=1)
        },
    })

BOT_EMAIL_RE = r'syncano\.bot\+(\d+|[a-f0-9]{32})@(syncano|gmail)\.com'

CELERY_TASK_ROUTES = {
    # analytics
    'apps.admins.tasks.NotifyAboutAdminSignup': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutResendAdminActivationEmail': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutAdminActivation': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutAdminPasswordReset': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutLogIn': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutLogInFailure': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutInvitation': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutSoftLimitReached': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutHardLimitReached': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutPaymentReceived': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.NotifyAboutPaymentFailure': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.AdminStateUpdater': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.MonthlySummaryTask': {
        'queue': DEFAULT_QUEUE
    },
    'apps.analytics.tasks.SendUnusedInstanceNotification': {
        'queue': DEFAULT_QUEUE
    },

    # backups
    'apps.backups.tasks.RunBackupTask': {
        'queue': BACKUPS_QUEUE
    },
    'apps.backups.tasks.RunRestoreTask': {
        'queue': BACKUPS_QUEUE
    },

    # codeboxes
    'apps.codeboxes.tasks.SchedulerDispatcher': {
        'queue': PERIODIC_SCHEDULERS_QUEUE
    },
    'apps.codeboxes.tasks.SchedulerTask': {
        'queue': PERIODIC_SCHEDULERS_QUEUE
    },
    'apps.codeboxes.tasks.CodeBoxRunTask': {
        'queue': CODEBOX_RUNNER_QUEUE
    },
    'apps.codeboxes.tasks.CodeBoxTask': {
        'queue': CODEBOX_QUEUE
    },
    'apps.codeboxes.tasks.ScheduleTask': {
        'queue': CODEBOX_QUEUE
    },
    'apps.codeboxes.tasks.SaveTraceTask': {
        'queue': CODEBOX_QUEUE
    },
    'apps.codeboxes.tasks.UpdateTraceTask': {
        'queue': CODEBOX_QUEUE
    },
    'apps.codeboxes.tasks.ScheduleNextTask': {
        'queue': CODEBOX_QUEUE
    },

    # webhooks
    'apps.webhooks.tasks.WebhookTask': {
        'queue': CODEBOX_QUEUE
    },

    # triggers
    'apps.triggers.tasks.TriggerTask': {
        'queue': CODEBOX_QUEUE
    },
    'apps.triggers.tasks.HandleTriggerEventTask': {
        'queue': CODEBOX_QUEUE
    },

    # metrics
    'apps.metrics.tasks.AggregateMinuteRunnerTask': {
        'queue': METRICS_QUEUE
    },
    'apps.metrics.tasks.AggregateHourRunnerTask': {
        'queue': METRICS_QUEUE
    },
    'apps.metrics.tasks.AggregateMinuteTask': {
        'queue': METRICS_QUEUE
    },
    'apps.metrics.tasks.AggregateHourTask': {
        'queue': METRICS_QUEUE
    },

    # core
    'apps.core.tasks.MasterMaintenanceTask': {
        'queue': DEFAULT_QUEUE
    },
    'apps.core.tasks.MaintenanceTask': {
        'queue': DEFAULT_QUEUE
    },
    'apps.core.tasks.DeleteLiveObjectTask': {
        'queue': DEFAULT_QUEUE
    },
    'apps.core.tasks.DeleteFilesTask': {
        'queue': DEFAULT_QUEUE
    },
    'apps.core.tasks.SyncInvalidationTask': {
        'queue': DEFAULT_QUEUE
    },

    # billing
    'apps.billing.tasks.ChargeOneHour': {
        'queue': DEFAULT_QUEUE
    },
    'apps.billing.tasks.InvoiceDispatcher': {
        'queue': DEFAULT_QUEUE
    },
    'apps.billing.tasks.CreateInvoiceCharge': {
        'queue': DEFAULT_QUEUE
    },
    'apps.billing.tasks.AggregateTransactions': {
        'queue': DEFAULT_QUEUE
    },
    'apps.billing.tasks.CheckSoftLimits': {
        'queue': DEFAULT_QUEUE
    },
    'apps.billing.tasks.CheckHardLimits': {
        'queue': DEFAULT_QUEUE
    },
    'apps.billing.tasks.create_stripe_customer': {
        'queue': DEFAULT_QUEUE
    },
    'apps.billing.tasks.remove_stripe_customer': {
        'queue': DEFAULT_QUEUE
    },
    'apps.billing.tasks.PlanFeeDispatcher': {
        'queue': DEFAULT_QUEUE
    },

    # push notifications
    'apps.push_notifications.tasks.SendGCMMessage': {
        'queue': PUSH_NOTIFICATIONS_QUEUE
    },
    'apps.push_notifications.tasks.SendAPNSMessage': {
        'queue': PUSH_NOTIFICATIONS_QUEUE
    },
    'apps.push_notifications.tasks.APNSFeedbackDispatcher': {
        'queue': PUSH_NOTIFICATIONS_QUEUE
    },
    'apps.push_notifications.tasks.GetAPNSFeedback': {
        'queue': PUSH_NOTIFICATIONS_QUEUE
    },

    # admins
    'apps.admins.tasks.RemoveBotAccounts': {
        'queue': DEFAULT_QUEUE
    },
    'apps.admins.tasks.DeleteInactiveAccounts': {
        'queue': DEFAULT_QUEUE
    },

    # data
    'apps.data.tasks.IndexKlassTask': {
        'queue': DEFAULT_QUEUE
    },

    # sockets
    'apps.sockets.tasks.SocketCheckerTask': {
        'queue': DEFAULT_QUEUE
    },
    'apps.sockets.tasks.SocketProcessorTask': {
        'queue': DEFAULT_QUEUE
    },
    'apps.sockets.tasks.SocketEnvironmentProcessorTask': {
        'queue': DEFAULT_QUEUE
    },
    'apps.sockets.tasks.AsyncScriptTask': {
        'queue': CODEBOX_QUEUE
    },

    # hosting
    'apps.hosting.tasks.HostingAddSecureCustomDomainTask': {
        'queue': ROOT_TASKS_QUEUE
    },
    'apps.hosting.tasks.HostingRefreshSecureCustomDomainCertTask': {
        'queue': ROOT_TASKS_QUEUE
    },
}

# Tracing
TRACING_ENABLED = os.environ.get('TRACING_ENABLED', 'true') == 'true'
TRACING_PERCENT = float(os.environ.get('TRACING_PERCENT', 100))
TRACING_SERVICE_NAME = 'platform-{}'.format(os.environ.get('INSTANCE_TYPE', 'web'))
ZIPKIN_ADDR = os.environ.get('ZIPKIN_ADDR', 'zipkin')
ZIPKIN_TIMEOUT = 3
ZIPKIN_RAISE = False

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# GITHUB
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET', '')

# LINKEDIN
LINKEDIN_CLIENT_ID = os.environ.get('LINKEDIN_CLIENT_ID', '')
LINKEDIN_CLIENT_SECRET = os.environ.get('LINKEDIN_CLIENT_SECRET', '')

# TWITTER
TWITTER_CLIENT_ID = os.environ.get('TWITTER_CLIENT_ID', '')
TWITTER_CLIENT_SECRET = os.environ.get('TWITTER_CLIENT_SECRET', '')

# Logging
COLORS_ENABLED = os.environ.get('COLORS_ENABLED', 'false') == 'true'
SENTRY_DSN = os.environ.get('SENTRY_DSN')
if SENTRY_DSN:
    RAVEN_CONFIG = {
        'dsn': SENTRY_DSN,
        'environment': LOCATION,
    }

LOGGING_HANDLERS = {
    'null': {
        'class': 'logging.NullHandler',
    },
    'console': {
        'level': 'DEBUG',
        'class': 'logging.StreamHandler',
        'formatter': 'verbose_color' if COLORS_ENABLED else 'verbose',
    },
    'console_task': {
        'level': 'DEBUG',
        'class': 'logging.StreamHandler',
        'formatter': 'verbose_task',
    },
    'sentry': {
        'level': 'ERROR',
        'class': 'raven.contrib.django.handlers.SentryHandler',
        'formatter': 'verbose',
    },
}

DEFAULT_HANDLERS = ['sentry', 'console']
TASKS_HANDLERS = ['sentry', 'console_task']

# Authorization for our log centralization solution
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'verbose': {
            'format': '%(levelname)-7s %(asctime)s %(name)s[%(filename)s:%(lineno)d]: %(message)s',
        },
        'verbose_color': {
            '()': 'celery.utils.log.ColorFormatter',
            'format': '%(levelname)-7s %(asctime)s %(name)s[%(filename)s:%(lineno)d]: %(message)s',
        },
        'verbose_task': {
            '()': 'celery.app.log.TaskFormatter',
            'format': '%(levelname)-7s %(asctime)s %(name)s '
                      '%(task_name)s[%(task_id)s][%(filename)s:%(lineno)d]: %(message)s',
        },
        'simple': {
            'format': '%(levelname)-7s: %(message)s'
        },
    },
    'handlers': LOGGING_HANDLERS,
    'root': {
        'handlers': DEFAULT_HANDLERS,
        'level': 'WARNING',
    },
    'loggers': {
        'celery': {
            'handlers': DEFAULT_HANDLERS,
            'level': 'INFO',
            'propagate': False,
        },
        'celery.redirected': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'celery_tasks': {
            'handlers': TASKS_HANDLERS,
            'level': 'INFO',
            'propagate': False,
        },
        'raven': {
            'handlers': DEFAULT_HANDLERS,
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': DEFAULT_HANDLERS,
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': DEFAULT_HANDLERS,
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security.DisallowedHost': {
            'handlers': ['null'],
            'propagate': False,
        },
        'django.security.TooManyFieldsSent': {
            'handlers': ['null'],
            'propagate': False,
        },
    }
}

if DEBUG:
    LOGGING['loggers']['django.db'] = {'handlers': DEFAULT_HANDLERS, 'level': 'DEBUG', 'propagate': False}

# Don't care that our email field in Admin is not unique, it's part of unique_together
SILENCED_SYSTEM_CHECKS = ['auth.E003']

# Django Dynamic Fixtures
DDF_FIELD_FIXTURES = {
    'apps.core.fields.DictionaryField': lambda: {},
    'jsonfield.fields.JSONField': lambda: None,
    'django.contrib.postgres.fields.hstore.HStoreField': lambda: {},
    'django.contrib.postgres.fields.array.ArrayField': lambda: [],
}

# Migrations
SCHEMA_MIGRATIONS_VERBOSITY = 0
CONCURRENT_MIGRATION_THREADS = int(os.environ.get('MIGRATION_THREADS', 4))
INITIAL_ADMIN_LAST_PK = 2
MIGRATION_CACHE = True
CONFIG_NAME = 'development'

# Legacy CodeBox & Docker
LEGACY_CODEBOX_ENABLED = os.environ.get('LEGACY_CODEBOX_ENABLED', 'false') == 'true'
DOCKER_VERSION = os.environ.get('DOCKER_VERSION', '1.26')
DOCKER_SHARED_DIRECTORY = os.environ.get('DOCKER_SHARED_DIRECTORY', '/home/syncano/app')
DOCKER_HOST_DIRECTORY = os.environ.get('DOCKER_HOST_DIRECTORY') or DOCKER_SHARED_DIRECTORY
CODEBOX_IMAGE_TAG = os.environ.get('CODEBOX_IMAGE_TAG', os.environ.get('CIRCLE_BRANCH', 'devel'))
CODEBOX_MOUNTED_SOURCE_DIRECTORY = '/app/source'
CODEBOX_MOUNTED_SOURCE_ENTRY_POINT = 'main'

CODEBOX_QUEUE_LIMIT_PER_RUNNER = 50
CODEBOX_PAYLOAD_SIZE_LIMIT = 512 * 1024
CODEBOX_PAYLOAD_CUTOFF = 64 * 1024
CODEBOX_RESULT_SIZE_LIMIT = 512 * 1024
CODEBOX_RESULT_CUTOFF = 64 * 1024
CODEBOX_SOURCE_CUTOFF = 64 * 1024
CODEBOX_SOURCE_SIZE_LIMIT = 3 * 1024 * 1024  # 3MB
TRIGGER_PAYLOAD_SIZE_LIMIT = 64 * 1024

# Codebox traces
CODEBOX_TRACE_TTL = 24 * 60 * 60
CODEBOX_TRACE_TRIMMED_TTL = 5 * 60


# Codebox timeouts
DEFAULT_SUBSCRIPTION_TIMEOUT = 3
WEBHOOK_MAX_TIMEOUT = int(os.environ.get('WEBHOOK_MAX_TIMEOUT', 300))  # 5 minutes
WEBHOOK_DEFAULT_TIMEOUT = int(os.environ.get('WEBHOOK_DEFAULT_TIMEOUT', 30))  # 30 seconds
CODEBOX_MAX_TIMEOUT = int(os.environ.get('CODEBOX_MAX_TIMEOUT', 300))  # 5 minutes
CODEBOX_DEFAULT_TIMEOUT = int(os.environ.get('CODEBOX_DEFAULT_TIMEOUT', 30))  # 30 seconds
SCHEDULE_MAX_TIMEOUT = int(os.environ.get('SCHEDULE_MAX_TIMEOUT', 300))  # 5 minutes
SCHEDULE_DEFAULT_TIMEOUT = int(os.environ.get('SCHEDULE_DEFAULT_TIMEOUT', 30))  # 30 seconds
TRIGGER_MAX_TIMEOUT = int(os.environ.get('TRIGGER_MAX_TIMEOUT', 300))  # 5 minutes
TRIGGER_DEFAULT_TIMEOUT = int(os.environ.get('TRIGGER_DEFAULT_TIMEOUT', 30))  # 30 seconds

# Codebox Schedule scheduling settings
CODEBOX_PER_INSTANCE_SCHEDULING_CHECK = 20
PERIODIC_SCHEDULE_MIN_INTERVAL = 30

# New Codebox settings
CODEBOX_GRPC_OPTIONS = [('grpc.keepalive_time_ms', 5000), ('grpc.keepalive_timeout_ms', 3000)]
CODEBOX_BROKER_UWSGI = os.environ.get('CODEBOX_BROKER_UWSGI', 'codebox-broker:8080')
CODEBOX_BROKER_GRPC = os.environ.get('CODEBOX_BROKER_GRPC', 'codebox-broker:9000')
CODEBOX_RELEASE = parse_date(os.environ.get('CODEBOX_RELEASE', '2017-01-01'))

# Metrics
METRICS_AGGREGATION_DELAY = {
    60: timedelta(minutes=1),  # Delay for minute aggregates
    60 * 60: timedelta(minutes=5),  # Delay for hour aggregates
    24 * 60 * 60: timedelta(minutes=10)  # Delay for day aggregates
}

# Core setup
POST_TRANSACTION_SUCCESS_EAGER = False
USER_GROUP_MAX_COUNT = 32
BATCH_MAX_SIZE = 50
USE_CSERIALIZER = os.environ.get('USE_CSERIALIZER', 'true') == 'true'
DEFAULT_ENDPOINT_ACL = {'*': ['get', 'list', 'update', 'delete']}
DEFAULT_SCRIPT_ENDPOINT_ACL = {'*': ['get', 'list']}

# Class
CLASS_MAX_INDEXES = 16
CLASS_MAX_FIELDS = 32
CREATE_INDEXES_CONCURRENTLY = True

# Data object
DATA_OBJECT_SIZE_MAX = 32768  # characters
DATA_OBJECT_STATEMENT_TIMEOUT = 1500  # milliseconds
DATA_OBJECT_INDEXING_RETRY = 10  # seconds
DATA_OBJECT_NESTED_QUERIES_MAX = 4
DATA_OBJECT_NESTED_QUERY_LIMIT = 1000
DATA_OBJECT_RELATION_LIMIT = 1000

# Channels and changes
CHANGES_TTL = 24 * 60 * 60
CHANGES_TRIMMED_TTL = 1 * 60 * 60
CHANNEL_MAX_ROOM_LENGTH = 128
CHANNEL_POLL_TIMEOUT = int(os.environ.get('CHANNEL_POLL_TIMEOUT', 5 * 60))  # 5 minutes
CHANNEL_TASK_TIMEOUT = int(os.environ.get('CHANNEL_TASK_TIMEOUT', 30))  # 30 seconds
CHANNEL_LAST_ID_TIMEOUT = int(os.environ.get('CHANNEL_LAST_ID_TIMEOUT', 2 * 60 * 60))  # 2 hours

# Hosting
HOSTING_DOMAIN = os.environ.get('HOSTING_DOMAIN', '.syncano.ninja')
HOSTING_SOCKETS_MAPPING_MAX = 20

# Sockets
SOCKETS_YAML = 'socket.yml'
SOCKETS_PROCESSOR_RETRY = 5  # seconds
SOCKETS_TASK_MAX_ATTEMPTS = 3
SOCKETS_MAX_ENDPOINTS = 30
SOCKETS_MAX_DEPENDENCIES = 100
SOCKETS_MAX_ZIP_FILE_FILES = 30
SOCKETS_MAX_PARSED_PAYLOAD = 512 * 1024  # 512kB
SOCKETS_MAX_PAYLOAD = 6 * 1024 * 1024  # 6MB
SOCKETS_MAX_RESULT_SIZE = 6 * 1024 * 1024  # 6 MB

SOCKETS_MAX_ZIP_FILE_SIZE = 15 * 1024 * 1024  # 15MB
SOCKETS_MAX_ENVIRONMENT_SIZE = 45 * 1024 * 1024  # 45MB
SOCKETS_MAX_SIZE = 25 * 1024 * 1024  # 25MB
SOCKETS_DEFAULT_VERSION = '0.1'
SOCKETS_MAX_CACHE_TIME = 30 * 60  # 30 minutes
SOCKETS_DEFAULT_TIMEOUT = 30  # 30 seconds
SOCKETS_MAX_TIMEOUT = 5 * 60  # 5 minutes
SOCKETS_DEFAULT_ASYNC = 0
SOCKETS_DEFAULT_MCPU = 0
SOCKETS_MAX_ASYNC = 100
SOCKETS_MAX_MCPU = 1000

DATA_UPLOAD_MAX_MEMORY_SIZE = SOCKETS_MAX_PAYLOAD

# CORS
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_HEADERS = (
    'x-requested-with',
    'content-type',
    'accept',
    'origin',
    'authorization',
    'x-api-key',
    'x-user-key',
)

# Billing
BILLING_DEFAULT_PLAN_NAME = os.environ.get('BILLING_DEFAULT_PLAN_NAME', 'builder')
BILLING_DEFAULT_PLAN_TIMEOUT = int(os.environ.get('BILLING_DEFAULT_PLAN_TIMEOUT', 30))  # days
BILLING_DEFAULT_DUE_DATE = 30  # days
BILLING_LIMIT_CHECK_TIMEOUT = 300  # seconds
BILLING_SUBSCRIPTION_CHECK_TIMEOUT = 300  # seconds
BILLING_INVOICES_CHECK_TIMEOUT = 600  # seconds
BILLING_GRACE_PERIOD_FOR_PLAN_CHANGING = 1  # hours
BILLING_DISPATCH_ALL_INVOICES = os.environ.get('BILLING_DISPATCH_ALL_INVOICES') == 'true'
BILLING_ALARM_POINTS = (80,)

BILLING_STORAGE_LIMITS = {'default': -1, 'builder': 10 * 1024 * 1024 * 1024}  # 10GB
BILLING_RATE_LIMITS = {'default': 60, 'builder': 60}
BILLING_POLL_RATE_LIMITS = {'default': 240, 'builder': 60}
BILLING_CONCURRENT_CODEBOXES = {'default': 8, 'builder': 2}
BILLING_INSTANCES_COUNT = {'default': 16, 'builder': 4}
BILLING_CLASSES_COUNT = {'default': 100, 'builder': 32}
BILLING_SOCKETS_COUNT = {'default': 100, 'builder': 32}
BILLING_SCHEDULES_COUNT = {'default': 100, 'builder': 32}

# Analytics
ANALYTICS_ENABLED = os.environ.get('ANALYTICS_ENABLED', 'true') == 'true'
ANALYTICS_WRITE_KEY = os.environ.get('ANALYTICS_WRITE_KEY', '')

# GUI
GUI_ROOT_URL = os.environ.get('GUI_ROOT_URL', 'https://dashboard.syncano.io')
GUI_ACTIVATION_URL = GUI_ROOT_URL + '/#/activate/%(uid)s/%(token)s'
GUI_CONFIRM_RESET_PASSWORD_URL = GUI_ROOT_URL + '/#/password/reset/%(uid)s/%(token)s'
GUI_BILLING_HISTORY_URL = GUI_ROOT_URL + '#account/invoices'
INVITATION_SITE_URL = GUI_ROOT_URL
GUI_PROLONG_URL = GUI_ROOT_URL + '/#/instances/?prolong'

# Stripe
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')

# After this time we send inactivity notice. 90 days by default.
ACCOUNT_MAX_IDLE_DAYS = int(os.environ.get('ACCOUNT_MAX_IDLE_TIME', 90))

# If notice was not confirmed we delete account after 14 days (by default) since sending notice
ACCOUNT_NOTICE_CONFIRMATION_DAYS = int(os.environ.get('ACCOUNT_NOTICE_CONFIRMATION_DAYS', 14))

PUSH_NOTIFICATIONS = {
    'APNS': {
        'ERROR_TIMEOUT': 3,
        'MAX_NOTIFICATION_SIZE': 2048,
        'PUSH_PORT': 2195,
        'FEEDBACK_PORT': 2196,
        'PRODUCTION': {
            'PUSH': 'gateway.push.apple.com',
            'FEEDBACK': 'feedback.push.apple.com',
        },
        'DEVELOPMENT': {
            'PUSH': 'gateway.sandbox.push.apple.com',
            'FEEDBACK': 'feedback.sandbox.push.apple.com',
        },
    }
}

BACKUPS_TEMPORARY_DIRECTORY = "/tmp/"
BACKUPS_PER_ACCOUNT_LIMIT = 75
