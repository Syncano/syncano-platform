from django.http import Http404
from rest_framework import status
from rest_framework.request import clone_request
from rest_framework.response import Response
from rest_framework.settings import api_settings


class CreateStripeResourceMixin:
    """Create a Stripe resource instance."""

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            self.resource = serializer.save()
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED,
                            headers=headers)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_success_headers(self, data):
        try:
            return {'Location': data[api_settings.URL_FIELD_NAME]}
        except (TypeError, KeyError):
            return {}


class RetrieveStripeResourceMixin:
    """Retrieve a Stripe resource instance."""

    def retrieve(self, request, *args, **kwargs):
        self.resource = self.retrieve_resource()
        serializer = self.get_serializer(self.resource)
        return Response(serializer.data)


class UpdateStripeResourceMixin:
    """Update a Stripe resource instance."""

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        self.resource = self.retrieve_resource_or_none()

        serializer = self.get_serializer(self.resource, data=request.data, partial=partial)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        response_status = status.HTTP_200_OK

        if self.resource is None:
            response_status = status.HTTP_201_CREATED

        self.resource = serializer.save()
        return Response(serializer.data, status=response_status)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def retrieve_resource_or_none(self):
        try:
            return self.retrieve_resource()
        except Http404:
            if self.request.method == 'PUT':
                self.check_permissions(clone_request(self.request, 'POST'))
            else:
                raise


class DestroyStripeResourceMixin:
    """Destroy a Stripe resource instance."""

    def destroy(self, request, *args, **kwargs):
        resource = self.retrieve_resource()
        resource.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
