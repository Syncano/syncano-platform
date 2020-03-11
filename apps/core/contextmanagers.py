# coding=UTF8
from contextlib import contextmanager


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
