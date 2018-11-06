# coding=UTF8
from django.conf import settings
from rest_framework import serializers

from apps.sockets.exceptions import SocketConfigWrongFormat, SocketMissingConfigVariable


class CustomSocketConfigValidator:
    @classmethod
    def validate_value(cls, variable_name, variable_meta, socket_config):
        if variable_meta.get('required') and variable_name not in socket_config:
            raise SocketMissingConfigVariable(variable_name)

    def validate(self, socket_config, meta_config):
        config_update = {}
        if not isinstance(meta_config, dict):
            raise SocketConfigWrongFormat()

        for variable_name, variable_meta in meta_config.items():
            if not isinstance(variable_name, str) or not isinstance(variable_meta, dict):
                raise SocketConfigWrongFormat()

            self.validate_value(variable_name, variable_meta, socket_config)

        socket_config.update(config_update)
        return socket_config


class FileListValidator:
    max_files_num = settings.SOCKETS_MAX_ZIP_FILE_FILES

    def __call__(self, value):
        if value is None:
            return
        if not isinstance(value, (tuple, list)):
            raise serializers.ValidationError('File list passed in invalid format.')
        if len(value) > self.max_files_num:
            raise serializers.ValidationError('Too many files defined (exceeds {max}).'.format(max=self.max_files_num))
