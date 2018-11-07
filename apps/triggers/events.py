# coding=UTF8
from rest_framework import serializers

from apps.core.helpers import Cached
from apps.data.models import Klass
from apps.triggers.validators import SignalValidator


class EventRegistry(dict):
    def register(self, event):
        self[event.source] = event

    def match(self, event_data):
        if isinstance(event_data, dict) and 'source' in event_data:
            event_class = self.get(event_data['source'])
            if event_class is not None:
                return event_class(event_data)


event_registry = EventRegistry()


class Event:
    DEFAULT_KEYS = {'source'}

    signals = set()
    source = None
    eh_prefix = None
    required_keys = None
    optional_keys = None

    def __init__(self, data):
        self.data = data

    def validate(self):
        keys = set(self.data.keys())

        required_keys = self.DEFAULT_KEYS
        if self.required_keys:
            required_keys = required_keys.union(self.required_keys)

        # Check optional keys if they are defined
        optional_keys = required_keys
        if self.optional_keys:
            optional_keys = required_keys.union(self.optional_keys)
        if keys.difference(optional_keys):
            raise serializers.ValidationError(
                'Event with {} source can only consist of: {}.'.format(self.source, ', '.join(optional_keys))
            )

        if not keys.issuperset(required_keys):
            raise serializers.ValidationError(
                'Event with {} source is required to define: {}.'.format(self.source, ', '.join(required_keys))
            )

        for key in keys:
            validate_func = getattr(self, 'validate_{}'.format(key), None)
            if validate_func is not None:
                self.data[key] = validate_func(self.data[key])

    def validate_signals(self, signals):
        signals = set(signals)
        if not signals:
            raise serializers.ValidationError(
                'Signals for {} requires at least one value. '
                'Possible values: {}.'.format(self.source, ', '.join(self.signals))
            )

        if not signals.issubset(self.signals):
            raise serializers.ValidationError(
                'Signals for event with {} source can only consist of: {}.'.format(self.source, ', '.join(self.signals))
            )
        return list(signals)

    def to_event_handler(self, signal):
        return '{}.{}'.format(self.eh_prefix, signal)


class DataObjectEvent(Event):
    signals = {'create', 'update', 'delete'}
    source = 'dataobject'
    required_keys = {'class'}

    def validate_class(self, value):
        try:
            klass = Cached(Klass, kwargs={'name': value}).get()
        except Klass.DoesNotExist:
            raise serializers.ValidationError('Referenced class does not exist.')
        return klass.name

    def to_event_handler(self, signal):
        return 'data.{}.{}'.format(self.data['class'], signal)


event_registry.register(DataObjectEvent)


class UserEvent(Event):
    signals = {'create', 'update', 'delete'}
    source = 'user'
    eh_prefix = 'data.user.'


event_registry.register(UserEvent)


class CustomEvent(Event):
    source = 'custom'
    eh_prefix = 'events'
    signal_validator = SignalValidator()

    def validate_signals(self, signals):
        if not signals:
            raise serializers.ValidationError(
                'Signals for {} requires at least one value.'.format(self.source)
            )

        signals = set(signals)
        for signal in signals:
            self.signal_validator(signal)

        return list(signals)


event_registry.register(CustomEvent)
