# coding=UTF8
from contextlib import contextmanager

from apps.data.models import DataObject


@contextmanager
def loaded_klass(klass):
    old_klass = getattr(DataObject, 'loaded_klass', None)
    DataObject.load_klass(klass)
    try:
        yield
    finally:
        if old_klass:
            DataObject.load_klass(old_klass)
