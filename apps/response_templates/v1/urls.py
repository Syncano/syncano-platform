# coding=UTF8
from rest_framework.routers import SimpleRouter

from apps.response_templates import views

router = SimpleRouter()

router.register(
    'snippets/templates',
    views.ResponseTemplateViewSet,
    base_name='response-templates'
)

urlpatterns = router.urls
