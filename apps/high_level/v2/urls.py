# coding=UTF8
from apps.core.routers import EndpointRouter
from apps.high_level.v2 import views

router = EndpointRouter()
router.register('endpoints/data', views.DataObjectHighLevelApiViewSet, base_name='hla-objects')

urlpatterns = router.urls
