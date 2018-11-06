from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path('', include(('apps.core.urls'))),
    path('v1/', include(('urls.api.v1', 'v1'))),
    path('v1.1/', include(('urls.api.v1_1', 'v1.1'))),
    path('v2/', include(('urls.api.v2', 'v2'))),
]

if settings.LOCAL_MEDIA_STORAGE:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
