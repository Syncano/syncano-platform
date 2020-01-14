# coding=UTF8
import os
import shutil

from django.core.cache import cache
from django.core.files.storage import default_storage

from apps.core.helpers import get_local_cache
from apps.core.middleware import clear_request_data


def create_storage_path(prefix='test'):
    return os.path.join(default_storage.base_location, prefix, str(os.getpid()))


class CleanupTestCaseMixin:
    def _pre_setup(self):
        cache.clear()
        clear_request_data()
        get_local_cache().clear()
        default_storage.location = create_storage_path()
        super()._pre_setup()

    def _post_teardown(self):
        storage_path = create_storage_path()
        if os.path.exists(storage_path):
            shutil.rmtree(storage_path)
        super()._post_teardown()
