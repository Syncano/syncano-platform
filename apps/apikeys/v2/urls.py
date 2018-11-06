# coding=UTF8
from rest_framework.routers import SimpleRouter

from apps.apikeys.v2 import views as v2_views

router = SimpleRouter()
router.register('api_keys', v2_views.ApiKeyViewSet)

urlpatterns = router.urls
