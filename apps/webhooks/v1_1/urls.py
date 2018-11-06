# coding=UTF8
from django.urls import path

from apps.core.routers import NestedSimpleRouter
from apps.webhooks.v1 import views as v1_views
from apps.webhooks.v1_1 import views

router = NestedSimpleRouter()

webhook_router = router.register('endpoints/scripts', views.WebhookViewSet, base_name='webhook')

webhook_router.register(
    'traces',
    v1_views.WebhookTraceViewSet,
    base_name='webhook-trace',
    parents_query_lookups=[
        'webhook',
    ]
)

urlpatterns = [
    path('endpoints/scripts/p/<public_link>/<name>/',
         v1_views.WebhookPublicView.as_view(),
         name='webhook-public-run-with-name'),
]

urlpatterns += router.urls
