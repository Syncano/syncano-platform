# coding=UTF8
import copyreg
import functools
from collections import Counter
from functools import partial
from operator import attrgetter

import psycopg2
import rapidjson as json
from django.apps import AppConfig as _AppConfig
from django.contrib.postgres.signals import get_citext_oids, get_hstore_oids
from django.db import ProgrammingError, connections, transaction
from django.db.backends.base.base import NO_DB_ALIAS
from django.db.backends.signals import connection_created
from django.db.models import signals, sql
from django.db.models.deletion import CASCADE, DO_NOTHING, Collector, get_candidate_relations_to_delete
from kombu.serialization import registry
from kombu.utils import json as _json
from psycopg2.extras import register_hstore
from raven.contrib.django.middleware import DjangoRestFrameworkCompatMiddleware

DELETION_MAX_CHUNK = 2000

# flake8: noqa
# A lot of custom django code here that doesn't pass mccabe check and we shouldn't exactly fix it
# as it would make porting to new version more difficult, so we need to disable flake8


def Collector__init(self, using=None):
    self._original_init(using)
    self.chunk_deletes = []


def Collector__collect(self, objs, source=None, nullable=False, collect_related=True,
                       source_attr=None, reverse_dependency=False, keep_parents=False):
    """
    NOTE: Original Django code. Only changes are marked as ADDED.
    Adds 'objs' to the collection of objects to be deleted as well as all
    parent instances.  'objs' must be a homogeneous iterable collection of
    model instances (e.g. a QuerySet).  If 'collect_related' is True,
    related objects will be handled by their respective on_delete handler.

    If the call is the result of a cascade, 'source' should be the model
    that caused it and 'nullable' should be set to True, if the relation
    can be null.

    If 'reverse_dependency' is True, 'source' will be deleted before the
    current model, rather than after. (Needed for cascading to parent
    models, the one case in which the cascade follows the forwards
    direction of an FK rather than the reverse direction.)

    If 'keep_parents' is True, data of parent model's will be not deleted.
    """
    if self.can_fast_delete(objs):
        self.fast_deletes.append(objs)
        return
    new_objs = self.add(objs, source, nullable,
                        reverse_dependency=reverse_dependency)
    if not new_objs:
        return

    model = new_objs[0].__class__

    if not keep_parents:
        # Recursively collect concrete model's parent models, but not their
        # related objects. These will be found by meta.get_fields()
        concrete_model = model._meta.concrete_model
        for ptr in concrete_model._meta.parents.values():
            if ptr:
                parent_objs = [getattr(obj, ptr.name) for obj in new_objs]
                self.collect(parent_objs, source=model,
                             source_attr=ptr.remote_field.related_name,
                             collect_related=False,
                             reverse_dependency=True)
    if collect_related:
        parents = model._meta.parents
        for related in get_candidate_relations_to_delete(model._meta):
            # Preserve parent reverse relationships if keep_parents=True.
            if keep_parents and related.model in parents:
                continue
            field = related.field
            if field.remote_field.on_delete == DO_NOTHING:
                continue
            batches = self.get_del_batches(new_objs, field)
            for batch in batches:
                sub_objs = self.related_objects(related, batch)
                if self.can_fast_delete(sub_objs, from_field=field):
                    self.fast_deletes.append(sub_objs)
                # ADDED:  (+3 lines)
                elif sub_objs.exists():
                    if field.remote_field.on_delete == CASCADE and sub_objs.count() >= DELETION_MAX_CHUNK:
                        self.chunk_deletes.append(sub_objs)
                    else:
                        field.remote_field.on_delete(self, field, sub_objs, self.using)
        for field in model._meta.private_fields:
            if hasattr(field, 'bulk_related_objects'):
                # It's something like generic foreign key.
                sub_objs = field.bulk_related_objects(new_objs, self.using)
                self.collect(sub_objs, source=model, nullable=True)


def Collector__delete(self):
    # NOTE: Original Django code. Only changes are marked as ADDED.

    # sort instance collections
    for model, instances in self.data.items():
        self.data[model] = sorted(instances, key=attrgetter("pk"))

    # if possible, bring the models in an order suitable for databases that
    # don't support transactions or cannot defer constraint checks until the
    # end of a transaction.
    self.sort()
    # number of objects deleted for each model label
    deleted_counter = Counter()

    with transaction.atomic(using=self.using, savepoint=False):
        # ADDED: Chunk deletion of larger amounts of related objects (+6 lines)
        for obj_queryset in self.chunk_deletes:
            exists = True
            while exists:
                values_list = obj_queryset.values_list('pk', flat=True)[:DELETION_MAX_CHUNK]
                obj_queryset.model.objects.filter(pk__in=values_list).delete()
                exists = obj_queryset.exists()

        # send pre_delete signals
        for model, obj in self.instances_with_model():
            if not model._meta.auto_created:
                signals.pre_delete.send(
                    sender=model, instance=obj, using=self.using
                )

        # fast deletes
        for qs in self.fast_deletes:
            count = qs._raw_delete(using=self.using)
            deleted_counter[qs.model._meta.label] += count

        # update fields
        for model, instances_for_fieldvalues in self.field_updates.items():
            for (field, value), instances in instances_for_fieldvalues.items():
                query = sql.UpdateQuery(model)
                query.update_batch([obj.pk for obj in instances],
                                   {field.name: value}, self.using)

        # reverse instance collections
        for instances in self.data.values():
            instances.reverse()

        # delete instances
        for model, instances in self.data.items():
            query = sql.DeleteQuery(model)
            pk_list = [obj.pk for obj in instances]
            count = query.delete_batch(pk_list, self.using)
            deleted_counter[model._meta.label] += count

            if not model._meta.auto_created:
                for obj in instances:
                    signals.post_delete.send(
                        sender=model, instance=obj, using=self.using
                    )

    # update collected instances
    for model, instances_for_fieldvalues in self.field_updates.items():
        for (field, value), instances in instances_for_fieldvalues.items():
            for obj in instances:
                setattr(obj, field.attname, value)
    for model, instances in self.data.items():
        for instance in instances:
            setattr(instance, model._meta.pk.attname, None)
    return sum(deleted_counter.values()), dict(deleted_counter)


@functools.lru_cache()
def get_hstore_oids(connection_alias):
    """Return hstore and hstore array OIDs."""
    with connections[connection_alias].cursor() as cursor:
        cursor.execute("SELECT 'hstore'::regtype::oid, 'hstore[]'::regtype::oid")
        oids = []
        array_oids = []
        for row in cursor:
            oids.append(row[0])
            array_oids.append(row[1])
        return tuple(oids), tuple(array_oids)


def register_type_handlers(connection, **kwargs):
    if connection.vendor != 'postgresql' or connection.alias == NO_DB_ALIAS:
        return

    try:
        oids, array_oids = get_hstore_oids(connection.alias)
        register_hstore(connection.connection, globally=False, oid=oids, array_oid=array_oids)
    except ProgrammingError:
        # Hstore is not available on the database.
        #
        # If someone tries to create an hstore field it will error there.
        # This is necessary as someone may be using PSQL without extensions
        # installed but be using other features of contrib.postgres.
        #
        # This is also needed in order to create the connection in order to
        # install the hstore extension.
        pass


class AppConfig(_AppConfig):
    name = 'apps.core'

    def __init__(self, app_name, app_module):
        # Add support for memoryview object (used in BinaryField) in pickle
        copyreg.pickle(memoryview, lambda b: (memoryview, (bytes(b),)))

        # Monkey patching cascade deletions of related objects
        # so they are chunked if there are more than 10000 objects.
        Collector._original_init = Collector.__init__
        Collector.__init__ = Collector__init
        Collector.collect = Collector__collect
        Collector.delete = Collector__delete

        # Register rapidjson for task serialization.
        registry.register('json',
                          json.dumps,
                          partial(_json.loads, _loads=json.loads),
                          content_type='application/json',
                          content_encoding='utf-8')

        # Disable request.body caching in raven middleware.
        DjangoRestFrameworkCompatMiddleware.process_request = lambda x, y: None
        super().__init__(app_name, app_module)

    def ready(self):
        from . import abstract_models, signal_handlers  # noqa

        connection_created.connect(register_type_handlers)
