# coding=UTF8
from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.backups.views import FullBackupViewSet, PartialBackupViewSet, RestoreViewSet, TopBackupsInstanceLinkView

router = SimpleRouter()
router.register('restores', RestoreViewSet, base_name="restores")
router.register('backups/full', FullBackupViewSet, base_name="full_backups")
router.register('backups/partial', PartialBackupViewSet, base_name="partial_backups")

urlpatterns = [path('backups/', TopBackupsInstanceLinkView.as_view(), name="instance_backups")]

urlpatterns += router.urls
