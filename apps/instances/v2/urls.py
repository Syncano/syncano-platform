# coding=UTF8
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.admins.views import AdminViewSet
from apps.instances.v2 import views

INSTANCE_PREFIX = '<instance>/'

instance_router = SimpleRouter()
instance_router.register('', views.InstanceViewSet, base_name='instance')

admins_router = SimpleRouter()
admins_router.register('admins', AdminViewSet, base_name='instance-admin')

urlpatterns = [
    path('', include(instance_router.urls)),
    path(INSTANCE_PREFIX, include(admins_router.urls)),
    path(INSTANCE_PREFIX, include('apps.data.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.codeboxes.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.invitations.v1.urls')),
    path(INSTANCE_PREFIX, include('apps.apikeys.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.triggers.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.webhooks.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.users.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.channels.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.high_level.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.batch.v1.urls')),
    path(INSTANCE_PREFIX, include('apps.push_notifications.v1.urls')),
    path(INSTANCE_PREFIX, include('apps.response_templates.v1.urls')),
    path(INSTANCE_PREFIX, include('apps.backups.v1.urls')),
    path(INSTANCE_PREFIX, include('apps.snippets.v1_1.urls')),
    path(INSTANCE_PREFIX, include('apps.endpoints.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.hosting.v2.urls')),
    path(INSTANCE_PREFIX, include('apps.sockets.v2.urls')),
]
