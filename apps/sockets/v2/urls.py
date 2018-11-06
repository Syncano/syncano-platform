# coding=UTF8
from apps.core.routers import NestedEndpointRouter
from apps.sockets.v2 import views

router = NestedEndpointRouter()

socket_router = router.register(
    'sockets',
    views.SocketViewSet,
    base_name='socket'
)

socket_router.register(
    'handlers',
    views.SocketHandlerViewSet,
    base_name='socket-handler',
    parents_query_lookups=[
        'socket',
    ]
)

endpoint_router = router.register(
    'endpoints/sockets',
    views.SocketEndpointViewSet,
    base_name='socket-endpoint'
)

endpoint_router.register(
    'traces',
    views.SocketEndpointTraceViewSet,
    base_name='socket-endpoint-trace',
    parents_query_lookups=[
        'socket_endpoint',
    ]
)

env_router = router.register(
    'environments',
    views.SocketEnvironmentViewSet,
    base_name='socket-environment'
)

urlpatterns = router.urls
