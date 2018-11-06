import stripe
from django.core.exceptions import ImproperlyConfigured
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response


class GenericStripeAPIView(GenericAPIView):
    resource = None

    # https://stripe.com/docs/api/python#expanding_objects
    expand = None

    def get_object(self, *args, **kwargs):
        return self.retrieve_resource(*args, **kwargs)

    def get_resource(self):
        if self.resource is not None:
            return self.resource

        error_format = "'%s' must define 'resource'"
        raise ImproperlyConfigured(error_format % self.__class__.__name__)

    def retrieve_resource(self, resource=None):
        if resource is None:
            resource = self.get_resource()

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup = self.kwargs.get(lookup_url_kwarg)

        if lookup is None:
            raise ImproperlyConfigured(
                'Expected view %s to be called with a URL keyword argument '
                'named "%s". Fix your URL conf, or set the `.lookup_field` '
                'attribute on the view correctly.' %
                (self.__class__.__name__, self.lookup_field)
            )

        params = self.filter_resource(resource)

        if self.expand:
            if not isinstance(self.expand, (list, tuple)):
                raise ImproperlyConfigured('"expand" attribute needs to be a list.')
            params['expand'] = self.expand

        obj = resource.retrieve(lookup, **params)
        self.check_object_permissions(self.request, obj)
        return obj

    def filter_resource(self, resource=None):
        return {}

    def handle_exception(self, exc):
        if not isinstance(exc, stripe.StripeError):
            return super().handle_exception(exc)

        if isinstance(exc, stripe.InvalidRequestError):
            return Response({'detail': str(exc)}, status=exc.http_status)

        raise
