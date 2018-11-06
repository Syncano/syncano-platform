# coding=UTF8
from livefield.managers import LiveManagerBase

from apps.core.querysets import LiveQuerySet

LiveManager = LiveManagerBase.from_queryset(LiveQuerySet)
