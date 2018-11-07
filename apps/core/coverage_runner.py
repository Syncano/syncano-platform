from django.apps import apps
from django.conf import global_settings, settings
from django.core.cache import caches
from django.test.runner import ParallelTestSuite as _ParallelTestSuite
from django.test.runner import _init_worker
from django.test.utils import get_runner
from django_redis import get_redis_connection

DjangoTestSuiteRunner = get_runner(global_settings)


def _custom_init_worker(counter):
    with counter.get_lock():
        _init_worker(counter)
        # Assign one redis db per worker
        redis_db = counter.value
        caches['default']._server = 'redis://{}:{}/{}'.format(settings.REDIS_HOST, settings.REDIS_PORT, redis_db)
        connection_pool = get_redis_connection().connection_pool
        connection_pool.connection_kwargs = connection_pool.connection_kwargs.copy()
        connection_pool.connection_kwargs['db'] = redis_db


class ParallelTestSuite(_ParallelTestSuite):
    init_worker = _custom_init_worker


class SyncanoTestRunner(DjangoTestSuiteRunner):
    app_modules = None
    parallel_test_suite = ParallelTestSuite

    def __init__(self, excluded_apps=None, **kwargs):
        super().__init__(**kwargs)
        self.excluded_apps = set(excluded_apps) if excluded_apps else set()

    @classmethod
    def add_arguments(cls, parser):
        super().add_arguments(parser)
        parser.add_argument('-e', '--exclude',
                            action='store', dest='excluded_apps',
                            nargs='*', help='Apps to exclude during tests.')

    def _find_best_app_module_match(self, module):
        app_modules = self._get_app_modules()
        for app_module in app_modules:
            if module == app_module or module.startswith('%s.' % app_module):
                return module
        raise LookupError("No installed app matching module '%s'." % module)

    def _get_app_modules(self):
        app_modules = self.app_modules
        if app_modules is None:
            app_modules = []

            for app in apps.get_app_configs():
                if app.module:
                    app_modules.append(app.module.__name__)
            app_modules.sort(key=len)

            self.app_modules = app_modules

        return app_modules

    def _prepare_modules(self, test_labels):
        if test_labels:
            test_modules = []

            for label in test_labels:
                app_label, _, submodule_path = label.partition('.')

                try:
                    test_module = apps.get_app_config(app_label).module.__name__
                    if submodule_path:
                        test_module += '.%s' % submodule_path
                except LookupError:
                    test_module = self._find_best_app_module_match(label)

                test_modules.append(test_module)
        else:
            test_modules = self._prepare_all_modules()

        return test_modules

    def _prepare_all_modules(self):
        test_modules = []

        for app in apps.get_app_configs():
            test_module = app.module.__name__
            if not test_module.startswith('apps.') \
                    or test_module in self.excluded_apps or app.label in self.excluded_apps:
                continue

            test_modules.append(test_module)
        return test_modules

    def run_tests(self, test_labels, extra_tests=None, **kwargs):
        test_modules = self._prepare_modules(test_labels)
        return super().run_tests(test_modules, extra_tests, **kwargs)
