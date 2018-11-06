# coding=UTF8
from django.conf import settings
from rest_framework.relations import PrimaryKeyRelatedField, SlugRelatedField
from rest_framework.serializers import ModelSerializer, ValidationError

from apps.admins.serializers import AdminFullSerializer
from apps.core.exceptions import PermissionDenied
from apps.core.field_serializers import DisplayedChoiceField, JSONField
from apps.core.mixins.serializers import HyperlinkedMixin, MetadataMixin

from .models import Backup, Restore
from .site import default_site


class BackupSerializer(MetadataMixin, ModelSerializer):
    instance = SlugRelatedField(slug_field='name',
                                required=False,
                                read_only=True,
                                allow_null=False)
    status = DisplayedChoiceField(Backup.STATUSES.as_choices(), read_only=True)
    author = AdminFullSerializer(read_only=True, source="owner")
    details = JSONField(read_only=True)

    class Meta:
        model = Backup
        read_only_fields = ('id', 'instance', 'created_at', 'updated_at',
                            'archive', 'size', 'status', 'status_info', 'author', 'details')
        fields = read_only_fields + ('description', 'label', 'query_args', 'metadata')
        extra_kwargs = {'description': {'required': False}, 'label': {'required': False}}


class FullBackupSerializer(HyperlinkedMixin, BackupSerializer):
    hyperlinks = (
        ('self', 'full_backups-toplevel-detail', ('id',)),
    )

    class Meta(BackupSerializer.Meta):
        fields = ('id', 'instance', 'created_at', 'updated_at', 'size',
                  'status', 'status_info', 'description', 'label', 'author', 'details', 'metadata')


class PartialBackupSerializer(HyperlinkedMixin, BackupSerializer):
    hyperlinks = (
        ('self', 'partial_backups-toplevel-detail', ('id',)),
    )
    query_args = JSONField(required=True, validators=[default_site.validate_query_args], write_only=True,
                           schema=lambda: default_site.jsonschema)


class RestoreSerializer(HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'restores-detail', ('instance.name', 'id')),
    )
    backup = PrimaryKeyRelatedField(required=False, allow_null=True,
                                    queryset=Backup.objects.none())
    status = DisplayedChoiceField(Backup.STATUSES.as_choices(), read_only=True)
    author = AdminFullSerializer(read_only=True, source="owner")

    class Meta:
        model = Restore
        fields = ('id', 'backup', 'created_at', 'updated_at', 'status', 'archive', 'status_info', 'author')
        read_only_fields = ('created_at', 'id', 'status', 'status_info', 'author')

    def get_fields(self):
        fields = super().get_fields()
        if 'request' in self.context:
            fields['backup'].queryset = Backup.objects.filter(
                owner=self.context['view'].request.user,
                status=Backup.STATUSES.SUCCESS,
                location=settings.LOCATION,
            )
        return fields

    def validate(self, attrs):
        has_archive = bool(attrs.get('archive', False))
        has_backup = bool(attrs.get('backup', False))
        if has_backup and has_archive or (not has_backup and not has_archive):
            raise ValidationError('You have to provide either backup or archive.')
        if has_archive and not self.context['request'].user.is_staff:
            raise PermissionDenied()
        return super().validate(attrs)
