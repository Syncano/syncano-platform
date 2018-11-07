# coding=UTF8
from django.conf import settings
from rest_framework import viewsets
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.reverse import reverse

from apps.billing.permissions import AdminInGoodStanding
from apps.controlpanel.permissions import IsStaffUser
from apps.core.mixins.views import AtomicMixin
from apps.core.views import LinksView
from apps.instances.mixins import InstanceBasedMixin

from .exceptions import CannotDeleteActiveBackup, TooManyBackups, TooManyBackupsRunning
from .models import Backup, Restore
from .serializers import BackupSerializer, FullBackupSerializer, PartialBackupSerializer, RestoreSerializer


class BackupsTopLevelViewSet(AtomicMixin, DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    model = Backup
    queryset = Backup.objects.all()
    serializer_class = BackupSerializer
    permission_classes = (
        AdminInGoodStanding,
        IsAuthenticated,
    )

    def get_queryset(self):
        return super().get_queryset().\
            filter(owner=self.request.user).select_related('owner', 'instance')

    def destroy(self, request, **kwds):
        backup = self.get_object()
        if backup.status in (backup.STATUSES.RUNNING, backup.STATUSES.UPLOADING):
            raise CannotDeleteActiveBackup()
        return super().destroy(request, **kwds)


class FullBackupsTopLevelViewSet(BackupsTopLevelViewSet):
    queryset = Backup.objects.filter(query_args={})
    serializer_class = FullBackupSerializer


class PartialBackupsTopLevelViewSet(BackupsTopLevelViewSet):
    queryset = Backup.objects.exclude(query_args={})
    serializer_class = PartialBackupSerializer
    permission_classes = (
        IsStaffUser,
    )


class RestoreViewSet(AtomicMixin, InstanceBasedMixin, CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    model = Restore
    queryset = Restore.objects.all()
    serializer_class = RestoreSerializer

    def perform_create(self, serializer):
        serializer.save(
            owner=self.request.user,
            target_instance=self.request.instance
        )

    def get_queryset(self):
        return super().get_queryset()\
            .filter(target_instance=self.request.instance).select_related('owner')


class BackupViewSet(AtomicMixin, DestroyModelMixin, InstanceBasedMixin,
                    CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    model = Backup
    queryset = Backup.objects.all()
    serializer_class = BackupSerializer

    def perform_create(self, serializer):
        backups = self.request.user.backups.all()

        if backups.filter(status__gte=Backup.STATUSES.SCHEDULED,
                          status__lt=Backup.STATUSES.SUCCESS).exists():
            raise TooManyBackupsRunning()

        # lock on admin to count backups
        Admin = type(self.request.user)
        admin = Admin.objects.select_for_update().get(pk=self.request.user.id)

        if backups.count() >= settings.BACKUPS_PER_ACCOUNT_LIMIT:
            raise TooManyBackups(settings.BACKUPS_PER_ACCOUNT_LIMIT)

        serializer.save(
            owner=admin,
            instance=self.request.instance
        )

    def get_queryset(self):
        return super().get_queryset().filter(instance=self.request.instance)

    def destroy(self, request, **kwds):
        backup = self.get_object()
        if backup.status not in (backup.STATUSES.SCHEDULED, backup.STATUSES.ABORTED,
                                 backup.STATUSES.ERROR, backup.STATUSES.SUCCESS,):
            raise CannotDeleteActiveBackup()
        return super().destroy(request, **kwds)


class FullBackupViewSet(BackupViewSet):
    queryset = Backup.objects.filter(query_args={})
    serializer_class = FullBackupSerializer


class PartialBackupViewSet(BackupViewSet):
    queryset = Backup.objects.exclude(query_args={})
    serializer_class = PartialBackupSerializer

    permission_classes = (
        IsStaffUser,
    )


class TopBackupsLinkView(LinksView):
    def generate_links(self):
        return {
            'full': reverse('full_backups-toplevel-list', request=self.request),
        }


class TopBackupsInstanceLinkView(InstanceBasedMixin, LinksView):
    def generate_links(self):
        return {
            'full': reverse('full_backups-list', args=(self.request.instance.name,), request=self.request),
        }
