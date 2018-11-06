# coding=UTF8
from rest_framework.routers import SimpleRouter

from apps.controlpanel import views

router = SimpleRouter()
router.register('admins', views.AdminViewSet, base_name='cp-admin')

urlpatterns = router.urls
