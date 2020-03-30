import os

import rapidjson as json
from django.core.files.storage import default_storage
from munch import Munch

from apps.backups import site
from apps.backups.options import ModelBackupByName

from .models import (
    Socket,
    SocketEndpoint,
    SocketEnvironment,
    SocketHandler,
    upload_custom_socket_file_to,
    upload_custom_socketenvironment_file_to
)


class SocketBackup(ModelBackupByName):
    include_details = 'count'
    details_lookup_field = 'name'

    def backup_object(self, storage, obj):
        if obj['zip_file']:
            obj['zip_file'] = storage.add_file(default_storage.open(obj['zip_file']))

        file_list = json.loads(obj['file_list'])
        for file_data in file_list.values():
            file_data['file'] = storage.add_file(default_storage.open(file_data['file']))
        obj['file_list'] = file_list

        super().backup_object(storage, obj)

    def to_instance(self, storage, representation):
        if representation['zip_file']:
            file_object = storage.get_file(representation['zip_file'])
            new_path = upload_custom_socket_file_to(Munch(representation), os.path.basename(file_object.name))
            default_storage.save(new_path, file_object)

        # Replace files from file_list with new ones
        file_list = representation.get('file_list', {})
        if not isinstance(file_list, dict):
            file_list = {}

        for path, file_data in file_list.items():
            f = storage.get_file(file_data['file'])
            new_path = Socket.get_storage_path_for_key(representation['key'], path)
            default_storage.save(new_path, f)
            file_data['file'] = new_path

        return super().to_instance(storage, representation)


class SocketEnvironmentBackup(ModelBackupByName):
    def backup_object(self, storage, obj):
        for f in ('zip_file', 'fs_file'):
            if obj[f]:
                obj[f] = storage.add_file(default_storage.open(obj[f]))

        super().backup_object(storage, obj)

    def to_instance(self, storage, representation):
        for f in ('zip_file', 'fs_file'):
            if f in representation and representation[f]:
                file_object = storage.get_file(representation[f])
                new_path = upload_custom_socketenvironment_file_to(Munch(representation),
                                                                   os.path.basename(file_object.name))
                default_storage.save(new_path, file_object)
                representation[f] = new_path

        return super().to_instance(storage, representation)


site.register(Socket, SocketBackup)
site.register(SocketEndpoint, ModelBackupByName)
site.register(SocketHandler)
site.register(SocketEnvironment, SocketEnvironmentBackup)
