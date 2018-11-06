# coding=UTF8
from rest_framework.reverse import reverse

from apps.core.views import LinksView
from apps.instances.mixins import InstanceBasedMixin


class TopEndpointsLinkView(InstanceBasedMixin, LinksView):
    links = (
        ('scripts', 'webhook-list'),
        ('data', 'hla-objects-list'),
    )

    def generate_links(self):
        return {name: reverse(viewname, args=(self.request.instance.name,), request=self.request)
                for name, viewname in self.links}
