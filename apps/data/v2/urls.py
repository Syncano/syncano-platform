# coding=UTF8
from apps.core.routers import NestedSimpleRouter
from apps.data.v2 import views as v2_views

router = NestedSimpleRouter()
class_router = router.register('classes', v2_views.KlassViewSet)
class_router.register('objects', v2_views.ObjectViewSet,
                      base_name='dataobject',
                      parents_query_lookups=['_klass'])

urlpatterns = router.urls
