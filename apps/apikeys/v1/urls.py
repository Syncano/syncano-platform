# coding=UTF8
from rest_framework.routers import SimpleRouter

from apps.apikeys.v1 import views

router = SimpleRouter()
router.register('api_keys', views.ApiKeyViewSet)

urlpatterns = router.urls
