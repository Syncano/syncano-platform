# coding=UTF8
from django.dispatch import Signal

codebox_finished = Signal(providing_args=["instance", "object_id", "trace"])
