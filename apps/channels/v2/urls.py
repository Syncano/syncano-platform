# coding=UTF8
from apps.channels.v2 import views as v2_views
from apps.core.routers import NestedSimpleRouter

router = NestedSimpleRouter()
channel_router = router.register('channels', v2_views.ChannelViewSet)
channel_router.register('history', v2_views.ChangeViewSet,
                        base_name='change',
                        parents_query_lookups=['channel'])

urlpatterns = router.urls
