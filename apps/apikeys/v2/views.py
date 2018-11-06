from apps.apikeys.v1 import views as v1_views
from apps.apikeys.v2.serializers import ApiKeySerializer


class ApiKeyViewSet(v1_views.ApiKeyViewSet):
    serializer_class = ApiKeySerializer
