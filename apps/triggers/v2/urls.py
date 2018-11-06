# coding=UTF8
from apps.core.routers import NestedSimpleRouter
from apps.triggers.v2 import views

router = NestedSimpleRouter()
trigger_router = router.register(
    'triggers',
    views.TriggerViewSet,
    base_name='trigger'
)

trigger_router.register(
    'traces',
    views.TriggerTraceViewSet,
    base_name='trigger-trace',
    parents_query_lookups=[
        'trigger',
    ]
)

urlpatterns = router.urls
