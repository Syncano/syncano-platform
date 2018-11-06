# coding=UTF8
from django.urls import include, path

from apps.core.routers import NestedSimpleRouter
from apps.core.social_proxies import GithubAuthProxyView, LinkedinAuthProxyView, TwitterAuthProxyView
from apps.users.v2 import views

router = NestedSimpleRouter()
users_router = router.register('users', views.UserViewSet, base_name='user')
users_router.register(
    'groups', views.UserMembershipViewSet, base_name='user-group',
    parents_query_lookups=['user', ]
)

groups_router = router.register('groups', views.GroupViewSet, base_name='group')
groups_router.register(
    'users', views.GroupMembershipViewSet, base_name='group-user',
    parents_query_lookups=['group', ]
)

urlpatterns = [
    path('users/auth/', views.UserAuthView.as_view(), name='user-authenticate'),
    path('users/me/', views.UserAccountView.as_view(), name='user-account'),
    path('users/auth/<backend>/', views.SocialAuthView.as_view(), name='authenticate_social_user'),
    path('users/auth/backend/github/proxy', GithubAuthProxyView.as_view(), name='user_github_auth_proxy'),
    path('users/auth/backend/linkedin/proxy', LinkedinAuthProxyView.as_view(), name='user_linkedin_auth_proxy'),
    path('users/auth/backend/twitter/proxy', TwitterAuthProxyView.as_view(), name='user_twitter_auth_proxy'),
    path('', include(router.urls)),
]
