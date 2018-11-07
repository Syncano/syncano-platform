# coding=UTF8
from django.conf import settings
from django.urls import include, path
from rest_framework.urlpatterns import format_suffix_patterns

from apps.core.views import TopLevelApiLinksView

urlpatterns = [
    path('', TopLevelApiLinksView.as_view(), name='links'),
    path('backups/', include('apps.backups.v1.urls_toplevel')),
    path('instances/', include('apps.instances.v1_1.urls')),
    path('cp/', include('apps.controlpanel.v1.urls')),
]

if settings.MAIN_LOCATION:
    urlpatterns += [
        path('account/', include('apps.admins.v1.urls')),
        path('billing/', include('apps.billing.v1.urls')),
        path('usage/', include('apps.metrics.v1.urls')),
    ]

urlpatterns = format_suffix_patterns(urlpatterns)
