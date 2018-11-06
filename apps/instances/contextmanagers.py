# coding=UTF8
from contextlib import contextmanager

from apps.instances.helpers import get_current_instance, set_current_instance


@contextmanager
def instance_context(instance):
    previous_instance = get_current_instance()
    try:
        set_current_instance(instance)
        yield
    finally:
        set_current_instance(previous_instance)
