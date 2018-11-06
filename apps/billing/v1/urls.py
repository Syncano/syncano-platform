# coding=UTF8
from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.billing import views

router = SimpleRouter()
router.register('coupons', views.CouponViewSet)
router.register('discounts', views.DiscountViewSet)
router.register('invoices', views.InvoiceViewSet)
router.register('events', views.EventViewSet, base_name='event')
router.register('subscriptions', views.SubscriptionViewSet)
router.register('plans', views.PricingPlanViewSet, base_name='plan')

urlpatterns = router.urls
profile_actions = {'get': 'retrieve', 'put': 'update', 'patch': 'partial_update'}
card_actions = {'get': 'retrieve', 'post': 'create', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}
limit_actions = {'get': 'retrieve'}

urlpatterns += path('profile/', views.ProfileViewSet.as_view(profile_actions), name='billing-profile'),
urlpatterns += path('card/', views.CardViewSet.as_view(card_actions), name='billing-card'),
