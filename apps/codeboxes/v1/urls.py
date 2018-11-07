# coding=UTF8
from apps.codeboxes.v1 import views
from apps.core.routers import NestedSimpleRouter

router = NestedSimpleRouter()
codeboxes_router = router.register(
    'codeboxes',
    views.CodeBoxViewSet,
    base_name='codebox'
)

codeboxes_router.register(
    'traces',
    views.CodeBoxTraceViewSet,
    base_name='codebox-trace',
    parents_query_lookups=[
        'codebox',
    ]
)

router.register(
    'codeboxes/runtimes',
    views.RuntimeViewSet,
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
