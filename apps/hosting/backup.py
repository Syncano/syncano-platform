# coding=UTF8
import os

from munch import Munch

from apps.backups import site
from apps.backups.options import ModelBackup
from apps.hosting.models import Hosting, HostingFile, upload_hosting_file_to


class HostingBackup(ModelBackup):
    include_details = 'count'

    def backup_object(self, storage, obj):
        # Remove CNAME and set ssl status to off on backup
        obj['ssl_status'] = Hosting.SSL_STATUSES.OFF
        cname = Hosting.find_cname(obj['domains'])
        if cname:
            obj['domains'].remove(cname)
        super().backup_object(storage, obj)


class HostingFileBackup(ModelBackup):
    include_details = 'count'

    def backup_object(self, storage, obj):
        path = obj['file_object']
        obj['file_object'] = storage.add_file(Hosting.get_storage().open(path))
        super().backup_object(storage, obj)

    def to_instance(self, storage, representation):
        file_object = storage.get_file(representation['file_object'])
        storage.update_storage_size(file_object.size)

        new_path = upload_hosting_file_to(Munch(representation), os.path.basename(file_object.name))
        Hosting.get_storage().save(new_path, file_object)
        representation['file_object'] = new_path
        return super().to_instance(storage, representation)


site.register(Hosting, HostingBackup)
site.register(HostingFile, HostingFileBackup)
