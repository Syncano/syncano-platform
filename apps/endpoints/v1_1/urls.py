# coding=UTF8
from django.urls import path

from apps.endpoints.v1_1 import views

urlpatterns = [
    path('endpoints/', views.TopEndpointsLinkView.as_view(), name='endpoints'),
]
