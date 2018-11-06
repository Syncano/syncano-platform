# coding=UTF8
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.admins import views
from apps.core.social_proxies import GithubAuthProxyView

admins_router = SimpleRouter()
admins_router.register('invitations', views.AdminInvitationViewSet, base_name='admin-invitation')


urlpatterns = [
    path('', include(admins_router.urls)),
    path('auth/', views.AuthView.as_view(), name='authenticate'),
    path('auth/<backend>/', views.SocialAuthView.as_view(), name='authenticate_social'),
    path('auth/backend/github/proxy', GithubAuthProxyView.as_view(), name='github_auth_proxy'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('resend_email/', views.ResendActivationEmailView.as_view(), name='resend_email'),
    path('', views.AccountView.as_view(), name='account'),
    path('reset_key/', views.AdminResetKey.as_view(), name='admin_reset_key'),
    path('password/', views.AdminChangePasswordView.as_view(), name='admin_change_password'),
    path('password/set/', views.AdminSetPasswordView.as_view(), name='admin_set_password'),
    path('password/reset/', views.AdminResetPasswordView.as_view(), name='admin_reset_password'),
    path('password/reset/confirm/', views.AdminResetPasswordConfirmationView.as_view(),
         name='admin_reset_password_confirm'),
    path('activate/', views.AdminActivationView.as_view(), name='admin-activate'),
]
