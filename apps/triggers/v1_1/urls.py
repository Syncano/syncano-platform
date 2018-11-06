# coding=UTF8
from apps.core.routers import NestedSimpleRouter
from apps.triggers.v1 import views as v1_views
from apps.triggers.v1_1 import views

router = NestedSimpleRouter()
trigger_router = router.register(
    'triggers',
    views.TriggerViewSet,
    base_name='trigger'
)

trigger_router.register(
    'traces',
    v1_views.TriggerTraceViewSet,
    base_name='trigger-trace',
    parents_query_lookups=[
        'trigger',
    ]
)

urlpatterns = router.urls
