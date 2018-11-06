# coding=UTF8
from apps.core.routers import NestedSimpleRouter
from apps.data.v1 import views

router = NestedSimpleRouter()
class_router = router.register('classes', views.KlassViewSet)
class_router.register('objects', views.ObjectViewSet,
                      base_name='dataobject',
                      parents_query_lookups=['_klass'],
                      post_as_update=True)

urlpatterns = router.urls
