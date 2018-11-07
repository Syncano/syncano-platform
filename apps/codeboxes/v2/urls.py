# coding=UTF8
from apps.codeboxes.v1 import views as v1_views
from apps.codeboxes.v2 import views
from apps.core.routers import NestedSimpleRouter

router = NestedSimpleRouter()
scripts_router = router.register(
    'snippets/scripts',
    views.CodeBoxViewSet,
    base_name='codebox'
)

scripts_router.register(
    'traces',
    views.CodeBoxTraceViewSet,
    base_name='codebox-trace',
    parents_query_lookups=[
        'codebox',
    ]
)

router.register(
    'snippets/scripts/runtimes',
    v1_views.RuntimeViewSet,
    base_name='runtime'
)

schedule_router = router.register(
    'schedules',
    views.ScheduleViewSet,
    base_name='codebox-schedule'
)

schedule_router.register(
    'traces',
    views.ScheduleTraceViewSet,
    base_name='schedule-trace',
    parents_query_lookups=[
        'schedule',
    ]
)

urlpatterns = router.urls
