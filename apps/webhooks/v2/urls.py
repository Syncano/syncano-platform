# coding=UTF8
from apps.core.routers import NestedEndpointRouter
from apps.webhooks.v2 import views

router = NestedEndpointRouter()

webhook_router = router.register('endpoints/scripts', views.WebhookViewSet, base_name='webhook')

webhook_router.register(
    'traces',
    views.WebhookTraceViewSet,
    base_name='webhook-trace',
    parents_query_lookups=[
        'webhook',
    ]
)

urlpatterns = router.urls
