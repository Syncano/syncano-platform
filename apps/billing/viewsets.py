from rest_framework.viewsets import ViewSetMixin

from apps.billing.generics import GenericStripeAPIView


class GenericStripeViewSet(ViewSetMixin, GenericStripeAPIView):
    """
    The GenericStripeViewSet class does not provide any actions by default,
    but does include the base set of generic view behavior, such as
    the `get_resource` and `retrieve_resource` methods.
    """
    pass
