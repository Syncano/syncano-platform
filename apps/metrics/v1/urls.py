# coding=UTF8
from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.metrics import views

router = SimpleRouter()
router.register('hourly', views.HourlyStatsViewSet, base_name='hour-aggregate')
router.register('daily', views.DailyStatsViewSet, base_name='day-aggregate')

urlpatterns = [
    path('', views.StatsLinksView.as_view(), name='stats'),
] + router.urls
