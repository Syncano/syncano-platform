# coding=UTF8
from rest_framework_extensions.routers import SimpleRouter

from apps.high_level.v1 import views as v1_views

router = SimpleRouter()
router.register('endpoints/data', v1_views.DataObjectHighLevelApiViewSet, base_name='hla-objects')

urlpatterns = router.urls
