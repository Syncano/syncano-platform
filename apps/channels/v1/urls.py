# coding=UTF8
from apps.channels.v1 import views
from apps.core.routers import NestedSimpleRouter

router = NestedSimpleRouter()
channel_router = router.register('channels', views.ChannelViewSet)
channel_router.register('history', views.ChangeViewSet,
                        base_name='change',
                        parents_query_lookups=['channel'])

urlpatterns = router.urls
