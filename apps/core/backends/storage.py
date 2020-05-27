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
from storages.utils import setting

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
        return super().url(name)

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

        return dest_name

    def size(self, name):
        filename = os.path.join(self.location, name)

        return os.path.getsize(filename)

    def delete_files(self, prefix, **kwargs):
        path_to_del = os.path.join(self.location, prefix)
        if os.path.exists(path_to_del):
            shutil.rmtree(path_to_del)
        return


class S3BotoStorage(StorageWithTransactionSupportMixin, s3boto3.S3Boto3Storage):
    def __init__(self, location=settings.LOCATION, storage_url=None, **settings):
        self._location = location
        self._storage_url = storage_url
        super().__init__(**settings)

    def internal_url(self, name):
        if self._storage_url:
            return self._storage_url + filepath_to_uri(name)
        return super().url(name)

    def copy(self, src_name, dest_name):
        src_name = self._normalize_name(self._clean_name(src_name))
        dest_name = self._normalize_name(self._clean_name(dest_name))

        self.bucket.copy(
            {'Bucket': self.bucket_name, 'Key': self._encode_name(src_name)},
            self._encode_name(dest_name),
            ExtraArgs={'ACL': settings.AWS_DEFAULT_ACL},
        )

        return dest_name

    def size(self, name):
        name = self._normalize_name(self._clean_name(name))
        return self.bucket.Object(self._encode_name(name)).content_length

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
            return self.copy(content.name, name)

        return super()._save(name, content)


class GoogleCloudStorage(StorageWithTransactionSupportMixin, gcloud.GoogleCloudStorage):
    preserve_acl = setting('GS_PRESERVE_ACL', True)

    def __init__(self, location=settings.LOCATION, storage_url=None, **settings):
        self._location = location
        self._storage_url = storage_url
        super().__init__(**settings)

    def internal_url(self, name):
        if self._storage_url:
            return self._storage_url + filepath_to_uri(name)

        # Remove unnecessary :443 from url that is created by boto for python > 2.7
        url = super().url(name)
        if ':443' in url:
            return url.replace(':443', '')
        return url

    def copy(self, src_name, dest_name):
        src_name = self._normalize_name(gcloud.clean_name(src_name))
        dest_name = self._normalize_name(gcloud.clean_name(dest_name))
        bucket = self.bucket

        source_blob = bucket.blob(self._encode_name(src_name))
        destination_blob = bucket.copy_blob(source_blob,
                                            bucket, self._encode_name(dest_name))

        if self.preserve_acl and self.default_acl:
            destination_blob.acl.save(acl=source_blob.acl)

        return dest_name

    def size(self, name):
        name = self._normalize_name(gcloud.clean_name(name))

        return self.bucket.get_blob(self._encode_name(name)).size

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
            return self.copy(content.name, name)

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
                'storage_url': get_loc_env(location, 'STORAGE_BUCKET_URL'),
            }
            opts.update(kwargs)
            return S3BotoStorage(location, **opts)

        if storage_type == 'gcs':
            opts = {
                'bucket_name': get_loc_env(location, 'STORAGE_BUCKET'),
                'credentials': service_account.Credentials.from_service_account_file(
                    get_loc_env(location, 'GOOGLE_APPLICATION_CREDENTIALS')),
                'storage_url': get_loc_env(location, 'STORAGE_BUCKET_URL'),
            }
            opts.update(kwargs)
            return GoogleCloudStorage(location, **opts)

        return FileSystemStorage(location)

    def _setup(self):
        self._wrapped = self.create_storage()
