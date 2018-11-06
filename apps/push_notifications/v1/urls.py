# coding=UTF8
from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.push_notifications import views

router = SimpleRouter()
router.register('push_notifications/gcm/devices', views.GCMDeviceViewSet, base_name='gcm-devices')
router.register('push_notifications/gcm/messages', views.GCMMessageViewSet, base_name='gcm-messages')
router.register('push_notifications/apns/devices', views.APNSDeviceViewSet, base_name='apns-devices')
router.register('push_notifications/apns/messages', views.APNSMessageViewSet, base_name='apns-messages')
config_actions = {'get': 'retrieve', 'put': 'update', 'patch': 'partial_update'}
remove_actions = {'post': 'remove_certificate'}

urlpatterns = [
    path('push_notifications/gcm/', views.GcmPushNotificationLinkView.as_view(), name='gcm-push'),
    path('push_notifications/apns/', views.APNSPushNotificationLinkView.as_view(), name='apns-push'),
    path('push_notifications/', views.TopPushNotificationLinkView.as_view(), name='push-notifications'),
    path('push_notifications/gcm/config/', views.GCMConfigViewSet.as_view(config_actions), name='gcm-config'),
    path('push_notifications/apns/config/', views.APNSConfigViewSet.as_view(config_actions), name='apns-config'),
    path('push_notifications/apns/config/remove_certificate/',
         views.APNSConfigViewSet.as_view(remove_actions), name='apns-remove-certificate'),
]

urlpatterns += router.urls
