# coding=UTF8
from apps.core.routers import NestedSimpleRouter
from apps.hosting.v1_1 import views

router = NestedSimpleRouter()

hosting_router = router.register(
    'hosting',
    views.HostingViewSet,
    base_name='hosting'
)

hosting_router.register(
    'files',
    views.HostingFileViewSet,
    base_name='hosting-file',
    parents_query_lookups=[
        'hosting',
    ]
)

urlpatterns = router.urls
