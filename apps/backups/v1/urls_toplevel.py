# coding=UTF8
from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.backups.views import FullBackupsTopLevelViewSet, PartialBackupsTopLevelViewSet, TopBackupsLinkView

backup_router = SimpleRouter()
backup_router.register('full', FullBackupsTopLevelViewSet, base_name='full_backups-toplevel')
backup_router.register('partial', PartialBackupsTopLevelViewSet, base_name='partial_backups-toplevel')

urlpatterns = [path('', TopBackupsLinkView.as_view(), name='backups')]

urlpatterns += backup_router.urls
