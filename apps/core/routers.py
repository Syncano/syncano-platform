# coding=UTF8
from django.urls import re_path
from rest_framework import routers
from rest_framework.routers import DynamicDetailRoute, DynamicListRoute, Route
from rest_framework_extensions import routers as ext_routers
from rest_framework_extensions.utils import compose_parent_pk_kwarg_name


class NestedRegistryItem(ext_routers.NestedRegistryItem):
    def __init__(self, router, parent_prefix, viewset_breadcrumb, parent_item=None):
        self.viewset_breadcrumb = viewset_breadcrumb
        super().__init__(router, parent_prefix, parent_item)

    def register(self, prefix, viewset, base_name, parents_query_lookups, post_as_update=False):
        self.router._register(
            prefix=self.get_prefix(current_prefix=prefix, parents_query_lookups=parents_query_lookups),
            viewset=viewset,
            base_name=base_name,
            viewset_breadcrumb=self.viewset_breadcrumb,
            parents_query_lookups=parents_query_lookups,
            post_as_update=post_as_update,
        )
        return NestedRegistryItem(
            router=self.router,
            parent_prefix=prefix,
            parent_item=self,
            viewset_breadcrumb=self.viewset_breadcrumb + [viewset, ]
        )

    def get_parent_prefix(self, parents_query_lookups):
        """
        Allow every character in parent prefix except for / (to separate url parts).
        """
        prefix = '/'
        current_item = self
        i = len(parents_query_lookups) - 1
        while current_item:
            lookup_value = getattr(current_item.viewset_breadcrumb[-1], 'lookup_value_regex', '[^/]+')

            prefix = '{parent_prefix}/(?P<{parent_pk_kwarg_name}>{lookup_value})/{prefix}'.format(
                parent_prefix=current_item.parent_prefix,
                parent_pk_kwarg_name=compose_parent_pk_kwarg_name(parents_query_lookups[i]),
                lookup_value=lookup_value,
                prefix=prefix
            )
            i -= 1
            current_item = current_item.parent_item
        return prefix.strip('/')


class EndpointRouterMixin:
    endpoint_routes = [
        # List route.
        Route(
            url=r'^{prefix}{trailing_slash}$',
            mapping={
                'get': 'list',
                'post': 'create'
            },
            name='{basename}-list',
            initkwargs={'suffix': 'List'}
        ),
        # Dynamically generated list routes.
        # Generated using @list_route decorator
        # on methods of the viewset.
        DynamicListRoute(
            url=r'^{prefix}/{methodname}{trailing_slash}$',
            name='{basename}-{methodnamehyphen}',
            initkwargs={}
        ),
        # Edit route.
        Route(
            url=r'^{prefix}/{lookup}/edit{trailing_slash}$',
            mapping={
                'get': 'retrieve',
                'put': 'update',
                'patch': 'partial_update',
                'delete': 'destroy'
            },
            name='{basename}-detail',
            initkwargs={'suffix': 'Instance'}
        ),
        # Dynamically generated detail routes.
        # Generated using @detail_route decorator on methods of the viewset.
        DynamicDetailRoute(
            url=r'^{prefix}/{lookup}/{methodname}{trailing_slash}$',
            name='{basename}-{methodnamehyphen}',
            initkwargs={}
        ),
        # Endpoint route.
        Route(
            url=r'^{prefix}/{lookup}{trailing_slash}$',
            mapping={
                'get': 'endpoint_get',
                'put': 'endpoint_put',
                'post': 'endpoint_post',
                'patch': 'endpoint_patch',
                'delete': 'endpoint_delete'
            },
            name='{basename}-endpoint',
            initkwargs={'suffix': 'Instance'}
        ),
    ]

    def __init__(self, *args, **kwargs):
        # Save original routes so we can switch them later on without modifying logic too much.
        self._routes = self.routes
        super().__init__(*args, **kwargs)

    def get_routes(self, viewset):
        if getattr(viewset, 'as_endpoint', False):
            self.routes = self.endpoint_routes
        else:
            self.routes = self._routes
        return super().get_routes(viewset)


class EndpointRouter(EndpointRouterMixin, routers.SimpleRouter):
    pass


class NestedSimpleRouter(ext_routers.NestedRouterMixin, routers.SimpleRouter):
    def _register(self, prefix, viewset, base_name=None, viewset_breadcrumb=None, parents_query_lookups=None,
                  post_as_update=False):
        if base_name is None:
            base_name = self.get_default_base_name(viewset)
        self.registry.append((prefix, viewset, base_name, viewset_breadcrumb, parents_query_lookups, post_as_update))

    def register(self, prefix, viewset, base_name=None, post_as_update=False):
        self._register(prefix=prefix, viewset=viewset, base_name=base_name, post_as_update=post_as_update)
        return NestedRegistryItem(
            router=self,
            parent_prefix=self.registry[-1][0],
            viewset_breadcrumb=[viewset]
        )

    def get_urls(self):
        """
        Use the registered viewsets to generate a list of URL patterns.
        """
        ret = []

        # Process registry in reverse order so that greedy regex matches (like .+) are checked last.
        for prefix, viewset, basename, viewset_breadcrumb, parents_query_lookups, post_as_update in self.registry[::-1]:
            lookup = self.get_lookup_regex(viewset)
            routes = self.get_routes(viewset)

            for route in routes:
                # Treat POST as update for one item instead of PUT
                if post_as_update and route.initkwargs.get('suffix') == 'Instance' \
                        and route.mapping.get('put') == 'update':
                    mapping = route.mapping.copy()
                    mapping['post'] = 'update'
                    del mapping['put']
                    route = route._replace(mapping=mapping)

                # Only actions which actually exist on the viewset will be bound
                mapping = self.get_method_map(viewset, route.mapping)
                if not mapping:
                    continue

                # Build the url pattern
                regex = route.url.format(
                    prefix=prefix,
                    lookup=lookup,
                    trailing_slash=self.trailing_slash
                )

                additional_kwargs = route.initkwargs.copy()
                if viewset_breadcrumb:
                    additional_kwargs['viewset_breadcrumb'] = viewset_breadcrumb
                if parents_query_lookups:
                    additional_kwargs['parents_query_lookups'] = parents_query_lookups

                view = viewset.as_view(mapping, **additional_kwargs)
                name = route.name.format(basename=basename)
                ret.append(re_path(regex, view, name=name))

        return ret


class NestedEndpointRouter(EndpointRouterMixin, NestedSimpleRouter):
    pass
