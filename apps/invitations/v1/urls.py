# coding=UTF8
from rest_framework.routers import SimpleRouter

from apps.invitations import views

router = SimpleRouter()
router.register('invitations', views.InvitationViewSet)

urlpatterns = router.urls
