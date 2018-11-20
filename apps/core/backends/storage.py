# coding=UTF8
from django.conf import settings
from django.core.files import storage
from django.db import DEFAULT_DB_ALIAS, connections
from django.utils.functional import LazyObject
from storages.backends import gcloud, s3boto3

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


class FileSystemStorage(StorageWithTransactionSupportMixin, storage.FileSystemStorage):
    def copy(self, src_name, dest_name):
        self.save(dest_name, self.open(src_name))


class S3BotoStorage(StorageWithTransactionSupportMixin, s3boto3.S3Boto3Storage):
    def copy(self, src_name, dest_name):
        self.bucket.copy(
            {'Bucket': self.bucket_name, 'Key': src_name},
            dest_name,
            ExtraArgs={'ACL': 'public-read'},
        )

    def _save(self, name, content):
        storage = getattr(content, '_storage', None)
        if storage and storage == self:
            cleaned_name = self._normalize_name(name)
            self.copy(content.name, cleaned_name)
            return cleaned_name
        return super()._save(name, content)


class GoogleCloudStorage(StorageWithTransactionSupportMixin, gcloud.GoogleCloudStorage):
    def copy(self, src_name, dest_name):
        bucket = self.bucket
        bucket.copy_blob(bucket.blob(src_name), bucket, dest_name)

    def _save(self, name, content):
        storage = getattr(content, '_storage', None)
        if storage and storage == self:
            cleaned_name = self._normalize_name(name)
            self.copy(content.name, cleaned_name)
            return cleaned_name
        return super()._save(name, content)


class DefaultStorage(LazyObject):
    # Common settings
    bucket = settings.STORAGE_BUCKET

    # S3 specific settings
    access_key = settings.S3_ACCESS_KEY_ID
    secret_key = settings.S3_SECRET_ACCESS_KEY
    region = settings.S3_REGION
    endpoint = settings.S3_ENDPOINT

    _file_storage = None

    @classmethod
    def create_storage(cls, **kwargs):
        if settings.STORAGE_TYPE == 's3':
            opts = {
                'access_key': cls.access_key,
                'secret_key': cls.secret_key,
                'bucket_name': cls.bucket,
                'region_name': cls.region,
                'endpoint_url': cls.endpoint
            }
            opts.update(kwargs)
            return S3BotoStorage(**opts)

        if settings.STORAGE_TYPE == 'gcloud':
            opts = {
                'bucket_name': cls.bucket,
            }
            opts.update(kwargs)
            return GoogleCloudStorage(**opts)

        if cls._file_storage is None:
            cls._file_storage = FileSystemStorage()
        return cls._file_storage

    def _setup(self):
        self._wrapped = self.create_storage()


default_storage = DefaultStorage()
