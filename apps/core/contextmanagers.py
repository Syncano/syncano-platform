# coding=UTF8
from contextlib import contextmanager

from django.db import IntegrityError, router, transaction


def blank_function(*args, **kwargs):
    pass


@contextmanager
def ignore_signal(*signals):
    for signal in signals:
        signal._send = signal.send
        signal.send = blank_function
    try:
        yield
    finally:
        for signal in signals:
            signal.send = signal._send


@contextmanager
def revalidate_integrityerror(model, validate_func):
    db = router.db_for_write(model)

    try:
        with transaction.atomic(db):
            yield
    except IntegrityError:
        validate_func()
        raise
