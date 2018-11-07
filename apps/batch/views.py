# coding=UTF8
from django.conf import settings
from rest_condition import Or
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.apikeys.permissions import IsApiKeyAccess
from apps.batch.exceptions import BatchLimitExceeded
from apps.batch.serializers import BatchSerializer
from apps.batch.utils import get_response, get_wsgi_request_object
from apps.billing.permissions import OwnerInGoodStanding
from apps.instances.mixins import InstanceBasedMixin


class BatchView(InstanceBasedMixin,
                generics.GenericAPIView):
    permission_classes = (
        OwnerInGoodStanding,
        Or(permissions.IsAuthenticated, IsApiKeyAccess)
    )
    serializer_class = BatchSerializer

    def get_queryset(self):
        # Workaround so that browsable API does not complain.
        return

    def create_headers(self, request):
        return {'X_BATCHING': '1'}

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            batch_limit = settings.BATCH_MAX_SIZE
            requests_data = serializer.data['requests']

            if len(requests_data) > batch_limit:
                raise BatchLimitExceeded(batch_limit)

            headers = self.create_headers(request)
            max_response_size = settings.MAX_RESPONSE_SIZE

            responses = []
            for data in requests_data:
                wsgi_request = get_wsgi_request_object(request._request,
                                                       method=data['method'],
                                                       url=data['path'],
                                                       headers=headers,
                                                       body=data['body'])
                response, response_len = get_response(wsgi_request, instance=request.instance)
                if 'content' in response:
                    max_response_size -= response_len
                    max_response_size = max(max_response_size, 0)
                responses.append(response)
            return Response(responses, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
