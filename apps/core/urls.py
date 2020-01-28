# coding=UTF8
from django.conf import settings
from django.urls import path

from apps.core.views import ApiLinksView, health_check, loader_token

urlpatterns = [
    path('%s/' % settings.LOADERIO_TOKEN, loader_token),
    path('healthz/', health_check),
    path('', ApiLinksView.as_view(), name='api-links'),
]
