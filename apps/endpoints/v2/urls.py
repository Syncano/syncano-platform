# coding=UTF8
from django.urls import path

from apps.endpoints.v2 import views

urlpatterns = [
    path('endpoints/', views.TopEndpointsLinkView.as_view(), name='endpoints'),
]
