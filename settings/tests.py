from datetime import date

from settings.common import *  # noqa, isort:skip

# Test settings
TESTING = True
CI = os.environ.get('CI', 'false') == 'true'
RESPONSE_ENCODED = False

# Setup to test multi database features during tests irrelevant of settings
DATABASES['instances']['NAME'] = 'instances'
DATABASES = {'default': DATABASES['default'], 'instances': DATABASES['instances']}

TEST_RUNNER = 'apps.core.coverage_runner.SyncanoTestRunner'
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True


# This disables migrations for given modules
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


# Disable migrations (due to big overhead) unless TEST_MIGRATIONS is true
if os.environ.get('TEST_MIGRATIONS', '') != 'true':
    MIGRATION_MODULES = DisableMigrations()

# Disable analytics
ANALYTICS_ENABLED = False

# Disable tracing
TRACING_ENABLED = False

# Force separate redis db
REDIS_DB = 1
CACHES['default']['LOCATION'] = 'redis://{}:{}/{}'.format(REDIS_HOST, REDIS_PORT, REDIS_DB),
CELERY_RESULT_BACKEND = 'redis://%s:%d/%d' % (REDIS_HOST, REDIS_PORT, REDIS_DB)

LOGGING['handlers']['console']['level'] = os.environ.get('TEST_LOG_LEVEL', 'ERROR')
LOGGING['handlers']['console_task']['level'] = os.environ.get('TEST_LOG_LEVEL', 'ERROR')

# Metrics
METRICS_AGGREGATION_DELAY = {
    60: timedelta(minutes=0),
    60 * 60: timedelta(minutes=0),
    24 * 60 * 60: timedelta(hours=0),
}

# Codebox settings
CODEBOX_RELEASE = date(2100, 1, 1)
CODEBOX_BROKER_UWSGI = 'localhost:8080'
