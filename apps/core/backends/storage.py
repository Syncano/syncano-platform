# coding=UTF8
from botocore.handlers import set_list_objects_encoding_type_url
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import DEFAULT_DB_ALIAS, connections
from django.utils.functional import LazyObject
from storages.backends.s3boto3 import S3Boto3Storage

from apps.core.helpers import add_post_transaction_error_operation, add_post_transaction_success_operation
from apps.instances.helpers import get_current_instance, get_instance_db


class StorageWithTransactionSupportMixin:
    def _get_current_db(self):
        instance = get_current_instance()
        if instance:
            db = get_instance_db(instance)
            # Check if we are in atomic block for that connection
            if connections[db].in_atomic_block:
                return db
        return DEFAULT_DB_ALIAS

    def url(self, name):
        # Remove unnecessary :443 from url that is created by boto for python > 2.7
        url = super().url(name)
        if ':443' in url:
            return url.replace(':443', '')
        return url

    def _save(self, name, content):
        name = super()._save(name, content)
        add_post_transaction_error_operation(super().delete,
                                             name,
                                             using=self._get_current_db())
        return name

    def delete(self, name):
        add_post_transaction_success_operation(super().delete,
                                               name,
                                               using=self._get_current_db())


class FileSystemStorageWithTransactionSupport(StorageWithTransactionSupportMixin, FileSystemStorage):
    def copy(self, src_name, dest_name):
        self.save(dest_name, self.open(src_name))


class S3BotoStorageWithTransactionSupport(StorageWithTransactionSupportMixin, S3Boto3Storage):
    def copy(self, src_name, dest_name):
        self.bucket.copy(
            {'Bucket': self.bucket_name, 'Key': src_name},
            dest_name,
            ExtraArgs={'ACL': 'public-read'},
        )

    def _save(self, name, content):
        storage = getattr(content, '_storage', None)
        if storage and storage == self:
            cleaned_name = self._clean_name(name)
            self.copy(content.name, cleaned_name)
            return cleaned_name
        return super()._save(name, content)

    @property
    def connection(self):
        connection = getattr(self._connections, 'connection', None)
        if connection is None:
            connection = super().connection
            connection.meta.client.meta.events.unregister('before-parameter-build.s3.ListObjects',
                                                          set_list_objects_encoding_type_url)
        return connection


class DefaultStorage(LazyObject):
    access_key = settings.S3_ACCESS_KEY_ID
    secret_key = settings.S3_SECRET_ACCESS_KEY
    bucket = settings.S3_STORAGE_BUCKET
    region = settings.S3_REGION
    endpoint = settings.S3_ENDPOINT

    _file_storage = None

    @classmethod
    def create_storage(cls, **kwargs):
        if settings.LOCAL_MEDIA_STORAGE:
            if cls._file_storage is None:
                cls._file_storage = FileSystemStorageWithTransactionSupport()
            return cls._file_storage

        opts = {
            'access_key': cls.access_key,
            'secret_key': cls.secret_key,
            'bucket_name': cls.bucket,
            'region_name': cls.region,
            'endpoint_url': cls.endpoint
        }
        opts.update(kwargs)
        return S3BotoStorageWithTransactionSupport(**opts)

    def _setup(self):
        self._wrapped = self.create_storage()


default_storage = DefaultStorage()
