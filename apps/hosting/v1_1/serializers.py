# coding=UTF8
import re
from hashlib import md5

from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from rest_framework.validators import UniqueValidator

from apps.core.field_serializers import DisplayedChoiceField, LowercaseCharField
from apps.core.helpers import add_post_transaction_success_operation
from apps.core.mixins.serializers import (
    DynamicFieldsMixin,
    HyperlinkedMixin,
    ProcessReadOnlyMixin,
    RemapperMixin,
    RevalidateMixin
)
from apps.hosting.exceptions import DomainAlreadyUsed, HostingLocked, OnlyOneDomainAllowed, PathAlreadyExists
from apps.hosting.models import Hosting, HostingFile
from apps.hosting.validators import VALID_DOMAIN_REGEX, DomainValidator, FilePathValidator, HostingNameValidator
from apps.instances.helpers import get_current_instance
from apps.instances.models import Instance


class HostingSerializer(DynamicFieldsMixin, HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'hosting-detail', (
            'instance.name',
            'pk',
        )),
        ('files', 'hosting-file-list', (
            'instance.name',
            'pk',
        )),
        ('set_default', 'hosting-set-default', (
            'instance.name',
            'pk',
        )),
        ('enable_ssl', 'hosting-enable-ssl', (
            'instance.name',
            'pk',
        )),
    )

    name = serializers.CharField(max_length=253, validators=[UniqueValidator(queryset=Hosting.objects.all()),
                                                             HostingNameValidator()])
    domains = serializers.ListField(
        child=LowercaseCharField(max_length=253, validators=[DomainValidator()]),
    )
    ssl_status = DisplayedChoiceField(choices=Hosting.SSL_STATUSES.as_choices(), read_only=True)

    class Meta:
        model = Hosting
        read_only_fields = ('is_default', )
        fields = ('id', 'name', 'is_default', 'description', 'created_at', 'updated_at', 'domains', 'is_active',
                  'ssl_status')

    def validate_domains(self, value):
        value_set = set(value)
        only_domains = [v for v in value_set if re.match(VALID_DOMAIN_REGEX, v)]
        # Only 1 domain per hosting allowed so that we can process SSL properly
        if len(only_domains) > 1:
            raise OnlyOneDomainAllowed()

        # this checks the global domains;
        if Instance.objects.exclude(pk=get_current_instance().pk).filter(
                domains__overlap=only_domains).exists():
            raise DomainAlreadyUsed()

        # prevent for creating hosting with the same domain;
        # but allow to update the same object with the same domains;
        validate_queryset = Hosting.objects.all()
        # update case; if empty - create case;
        current_hosting = self.instance
        if current_hosting:
            validate_queryset = validate_queryset.exclude(pk=current_hosting.pk)

        # use a all values here - this will check if no two hosting objects exists with the same instance name
        # and suffix combination;
        if validate_queryset.filter(domains__overlap=list(value_set)).exists():
            raise DomainAlreadyUsed()

        return list(value_set)

    def validate(self, data):
        if self.instance and self.instance.is_locked:
            raise HostingLocked()
        return super().validate(data)

    def to_internal_value(self, data):
        reverted_data = super().to_internal_value(data)
        # Automatically add name to domains
        if reverted_data:
            if 'name' in reverted_data:
                name = reverted_data['name']
            else:
                name = self.instance.name

            if 'domains' in reverted_data:
                domains = reverted_data['domains']
            else:
                domains = self.instance

            if isinstance(domains, list):
                if name not in domains:
                    domains.append(name)
            else:
                reverted_data['domains'] = [name]
        return reverted_data


class HostingDetailSerializerMixin(ProcessReadOnlyMixin):
    additional_read_only_fields = ('name', )


class HostingDetailSerializer(HostingDetailSerializerMixin, HostingSerializer):
    pass


class HostingFileSerializer(DynamicFieldsMixin, HyperlinkedMixin, RemapperMixin, RevalidateMixin, ModelSerializer):

    hyperlinks = (
        ('self', 'hosting-file-detail', (
            'instance.name',
            'hosting.id',
            'pk'
        )),
    )

    field_mappings = {'file_object': 'file'}

    path = serializers.CharField(
        required=True,
        validators=[FilePathValidator()]
    )

    class Meta:
        model = HostingFile
        fields = ('id', 'path', 'size', 'file_object', 'checksum')
        extra_kwargs = {
            'size': {'read_only': True},
            'checksum': {'read_only': True},
            'file_object': {'write_only': True, 'allow_empty_file': True}
        }

    def to_internal_value(self, data):
        reverted_data = super().to_internal_value(data)

        if reverted_data is None:
            return reverted_data

        if 'view' in self.context:
            reverted_data['hosting'] = self.context['view'].hosting
        if 'path' in reverted_data:
            reverted_data['level'] = reverted_data['path'].count('/')
        if 'file_object' in reverted_data:
            reverted_data['size'] = reverted_data['file_object'].size

            hash_md5 = md5()
            for chunk in reverted_data['file_object'].chunks():
                hash_md5.update(chunk)
            reverted_data['checksum'] = hash_md5.hexdigest()
        return reverted_data

    def validate(self, data):
        if 'path' in data and 'view' in self.context:
            qs = HostingFile.objects.filter(hosting=self.context['view'].hosting, path=data['path'])
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise PathAlreadyExists()
        return data

    def update(self, instance, validated_data):
        old_file_name = instance.file_object.name
        updated_instance = super().update(instance, validated_data)
        # force to delete old file;
        add_post_transaction_success_operation(instance.file_object.storage.delete, old_file_name)
        return updated_instance


class HostingFileDetailSerializer(ProcessReadOnlyMixin, HostingFileSerializer):
    additional_read_only_fields = ('path',)
