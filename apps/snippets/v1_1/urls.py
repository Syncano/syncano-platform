# coding=UTF8
from django.urls import path

from apps.snippets import views

urlpatterns = [
    path('snippets/', views.TopSnippetsLinkView.as_view(), name='snippets'),
    path('snippets/config/', views.InstanceConfigView.as_view(), name='instance-config'),
]
