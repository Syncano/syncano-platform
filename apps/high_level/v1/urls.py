# coding=UTF8
from rest_framework_extensions.routers import SimpleRouter

from apps.high_level.v1 import views

router = SimpleRouter()
router.register('api/objects', views.DataObjectHighLevelApiViewSet, base_name='hla-objects')

urlpatterns = router.urls
