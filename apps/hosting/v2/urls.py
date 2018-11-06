# coding=UTF8
from apps.core.routers import NestedSimpleRouter
from apps.hosting.v1_1 import views as v1_1_views
from apps.hosting.v2 import views as v2_views

router = NestedSimpleRouter()

hosting_router = router.register(
    'hosting',
    v2_views.HostingViewSet,
    base_name='hosting'
)

hosting_router.register(
    'files',
    v1_1_views.HostingFileViewSet,
    base_name='hosting-file',
    parents_query_lookups=[
        'hosting',
    ]
)

urlpatterns = router.urls
