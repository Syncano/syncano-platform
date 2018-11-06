# coding=UTF8
from apps.endpoints.v1_1 import views as v1_1_views


class TopEndpointsLinkView(v1_1_views.TopEndpointsLinkView):
    links = (
        ('scripts', 'webhook-list'),
        ('data', 'hla-objects-list'),
        ('sockets', 'socket-endpoint-list'),
    )
