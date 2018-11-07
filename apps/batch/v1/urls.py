# coding=UTF8
from django.urls import path

from apps.batch import views

urlpatterns = [
    path('batch/', views.BatchView.as_view(), name='batch'),
]
