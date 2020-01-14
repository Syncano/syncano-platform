# coding=UTF8
import os
from collections import defaultdict

from django.core.files.storage import default_storage
from munch import Munch

from apps.backups import site
from apps.backups.options import ModelBackup
from apps.data.tasks import IndexKlassTask
from apps.instances.helpers import get_current_instance

from .exceptions import KlassCountExceeded
from .helpers import upload_file_to
from .models import DataObject, Klass


class KlassBackup(ModelBackup):
    lookup_field = 'name'
    include_details = 'list'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = get_current_instance()

    def to_instance(self, storage, representation):
        # remove existing_indexes, because there are no indexes yes
        representation.pop('existing_indexes', None)
        return super().to_instance(storage, representation)

    def save_batch(self, object_list, restore_context=None):
        klass_limit = self.instance.owner.admin_limit.get_classes_count()
        if self.model.objects.count() + len(object_list) > klass_limit:
            raise KlassCountExceeded(klass_limit)

        super().save_batch(object_list, restore_context)

        klass_queryset = Klass.objects.only('existing_indexes', 'schema', 'mapping')
        for klass in klass_queryset.filter(pk__in=[obj.pk for obj in object_list]):
            index_changes, _ = Klass.process_index_changes(klass.existing_indexes,
                                                           [], klass.schema,
                                                           {}, klass.mapping)
            if index_changes:
                index_changes_done = defaultdict(list)
                IndexKlassTask.process_indexes(instance=self.instance,
                                               klass_pk=klass.pk,
                                               index_changes=index_changes,
                                               concurrently=False,
                                               record_done=index_changes_done)
                klass.unlock(index_changes_done)


class DataObjectBackup(ModelBackup):
    include_details = 'count'

    def backup_object(self, storage, obj):
        for key in obj['_files']:
            path = obj['_data'][key]
            obj['_data'][key] = storage.add_file(default_storage.open(path))
        super().backup_object(storage, obj)

    def restore(self, storage, restore_context=None):
        # Get rid of any schema associated with DataObject, because it could
        # introduce other Klass-es fields to _data dictionary
        DataObject._meta.get_field('_data').reload_schema(None)
        return super().restore(storage, restore_context)

    def to_instance(self, storage, representation):
        for file_field in representation['_files']:
            file = storage.get_file(representation['_data'][file_field])
            storage.update_storage_size(file.size)

            new_path = upload_file_to(Munch(representation), os.path.basename(file.name))
            default_storage.save(new_path, file)
            representation['_data'][file_field] = new_path
        return super().to_instance(storage, representation)


site.register(Klass, KlassBackup)
site.register(DataObject, DataObjectBackup)
