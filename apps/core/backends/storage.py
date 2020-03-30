# coding=UTF8
import os
import shutil

from django.conf import settings
from django.core.files import storage
from django.db import DEFAULT_DB_ALIAS, connections
from django.utils.encoding import filepath_to_uri
from django.utils.functional import LazyObject
from google.oauth2 import service_account
from storages.backends import gcloud, s3boto3

from apps.core.helpers import add_post_transaction_error_operation, add_post_transaction_success_operation, get_loc_env
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

    def internal_url(self, name):
        # Remove unnecessary :443 from url that is created by boto for python > 2.7
        url = super().url(name)
        if ':443' in url:
            return url.replace(':443', '')
        return url

    def url(self, name):
        if settings.STORAGE_URL:
            return settings.STORAGE_URL + filepath_to_uri(name)
        return self.internal_url(name)

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
    def __init__(self, location=settings.LOCATION, **settings):
        self._location = location
        super().__init__(**settings)

    def copy(self, src_name, dest_name):
        self.save(dest_name, self.open(src_name))

    def delete_files(self, prefix, **kwargs):
        path_to_del = os.path.join(self.location, prefix)
        if os.path.exists(path_to_del):
            shutil.rmtree(path_to_del)
        return


class S3BotoStorage(StorageWithTransactionSupportMixin, s3boto3.S3Boto3Storage):
    def __init__(self, location=settings.LOCATION, **settings):
        self._location = location
        super().__init__(**settings)

    def copy(self, src_name, dest_name):
        self.bucket.copy(
            {'Bucket': self.bucket_name, 'Key': src_name},
            dest_name,
            ExtraArgs={'ACL': settings.AWS_DEFAULT_ACL},
        )

    def delete_files(self, prefix, buckets, **kwargs):
        if not prefix.endswith('/'):
            prefix += '/'

        for bucket_name in buckets:
            bucket_name = get_loc_env(self._location, bucket_name)

            self.connection.Bucket(bucket_name).objects.filter(Prefix=prefix).delete()
        return

    def _save(self, name, content):
        storage = getattr(content, '_storage', None)

        if storage and storage == self:
            # If already exists, just copy it.
            cleaned_name = self._normalize_name(name)
            self.copy(content.name, cleaned_name)
            return cleaned_name

        return super()._save(name, content)


class GoogleCloudStorage(StorageWithTransactionSupportMixin, gcloud.GoogleCloudStorage):
    def __init__(self, location=settings.LOCATION, **settings):
        self._location = location
        super().__init__(**settings)

    def copy(self, src_name, dest_name):
        bucket = self.bucket
        bucket.copy_blob(bucket.blob(src_name), bucket, dest_name)

    def delete(self, name):
        name = self._normalize_name(gcloud.clean_name(name))
        self.bucket.delete_blobs([self._encode_name(name)], on_error=lambda blob: None)

    def delete_files(self, prefix, buckets, **kwargs):
        if not prefix.endswith('/'):
            prefix += '/'

        for bucket_name in buckets:
            bucket_name = get_loc_env(self._location, bucket_name)
            bucket = self.client.get_bucket(bucket_name)

            for blob in bucket.list_blobs(prefix=prefix):
                blob.delete()
        return

    def _save(self, name, content):
        storage = getattr(content, '_storage', None)

        if storage and storage == self:
            # If already exists, just copy it.
            cleaned_name = self._normalize_name(name)
            self.copy(content.name, cleaned_name)
            return cleaned_name

        return super()._save(name, content)


class DefaultStorage(LazyObject):
    _cache = {}

    @classmethod
    def create_storage(cls, location=settings.LOCATION, **kwargs):
        storage_type = get_loc_env(location, 'STORAGE', 'local')
        if storage_type == 'local':
            cache_key = storage_type
        else:
            cache_key = (location, frozenset(kwargs.items()))

        if cache_key in cls._cache:
            return cls._cache[cache_key]

        storage = cls._create_storage(storage_type, location, **kwargs)
        cls._cache[cache_key] = storage
        return storage

    @classmethod
    def _create_storage(cls, storage_type, location, **kwargs):
        if storage_type == 's3':
            opts = {
                'bucket_name': get_loc_env(location, 'STORAGE_BUCKET'),
                'access_key': get_loc_env(location, 'S3_ACCESS_KEY_ID'),
                'secret_key': get_loc_env(location, 'S3_SECRET_ACCESS_KEY'),
                'region_name': get_loc_env(location, 'S3_REGION'),
                'endpoint_url': get_loc_env(location, 'S3_ENDPOINT'),
            }
            opts.update(kwargs)
            return S3BotoStorage(location, **opts)

        if storage_type == 'gcs':
            opts = {
                'bucket_name': get_loc_env(location, 'STORAGE_BUCKET'),
                'credentials': service_account.Credentials.from_service_account_file(
                    get_loc_env(location, 'GOOGLE_APPLICATION_CREDENTIALS')),
            }
            opts.update(kwargs)
            return GoogleCloudStorage(location, **opts)

        return FileSystemStorage(location)

    def _setup(self):
        self._wrapped = self.create_storage()
