import logging
from datetime import date, timedelta

import rapidjson as json
import stripe
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404
from django.utils import timezone
from psycopg2.extras import DateRange
from rest_framework import generics, mixins, permissions, status
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet, ViewSet

from apps.admins.models import Admin
from apps.billing.exceptions import CannotCancelUnpaidSubscription, InvalidInvoiceStatus, PaymentFailed, StripeCardError
from apps.core.helpers import Cached, get_from_request_data
from apps.core.mixins.views import AtomicMixin
from apps.core.renderers import PDFRenderer
from apps.instances.models import Instance

from .mixins import (
    CreateStripeResourceMixin,
    DestroyStripeResourceMixin,
    RetrieveStripeResourceMixin,
    UpdateStripeResourceMixin
)
from .models import Coupon, Discount, Event, Invoice, InvoiceItem, PricingPlan, Profile, Subscription
from .serializers import (
    CouponRedemptionSerializer,
    CouponSerializer,
    DiscountSerializer,
    InvoicePdfSerializer,
    InvoiceSerializer,
    PricingPlanSerializer,
    PricingPlanSubscribeSerializer,
    ProfileSerializer,
    StripeCardSerializer,
    StripeTokenSerializer,
    SubscriptionSerializer
)
from .viewsets import GenericStripeViewSet

logger = logging.getLogger(__name__)
COUPON_DOESNT_EXIST = {"coupon": ["Coupon doesn't exist."]}
INSTANCE_DOESNT_EXIST = {"instance": ["Instance doesn't exist."]}


class CouponViewSet(AtomicMixin,
                    mixins.ListModelMixin,
                    mixins.CreateModelMixin,
                    mixins.RetrieveModelMixin,
                    mixins.DestroyModelMixin,
                    GenericViewSet):
    """API for coupons.

    User has to be identified as staff to create and browse coupons.
    """
    lookup_field = 'name'
    model = Coupon
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer

    permission_classes = (
        permissions.IsAuthenticated,
        permissions.IsAdminUser,
    )


class DiscountViewSet(AtomicMixin,
                      mixins.ListModelMixin,
                      mixins.CreateModelMixin,
                      mixins.RetrieveModelMixin,
                      GenericViewSet):
    """API for discounts"""
    model = Discount
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CouponRedemptionSerializer
        return self.serializer_class

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(customer=self.request.user)

    def create(self, request, *args, **kwargs):
        """Create new discount by redeeming a coupon"""
        try:
            try:
                coupon = Coupon.objects.get(name=get_from_request_data(request, 'coupon'))
            except Coupon.DoesNotExist:
                return Response(COUPON_DOESNT_EXIST, status=status.HTTP_400_BAD_REQUEST)
            try:
                # this way should support both name and primary key (only supported option in django rest framework)
                instance_identifier = get_from_request_data(request, 'instance')
                if isinstance(instance_identifier, int):
                    instance = Cached(Instance, kwargs=dict(pk=instance_identifier)).get()
                else:
                    instance = Cached(Instance, kwargs=dict(name=instance_identifier)).get()
            except Instance.DoesNotExist:
                return Response(INSTANCE_DOESNT_EXIST, status=status.HTTP_400_BAD_REQUEST)
            customer = request.user
            discount = coupon.redeem(instance=instance, customer=customer)
            serialized_discount = DiscountSerializer(discount, context={'request': request})

            return Response(serialized_discount.data, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response(e.message_dict, status=status.HTTP_400_BAD_REQUEST)


class InvoiceViewSet(AtomicMixin,
                     ReadOnlyModelViewSet):
    """API for details & list of your invoices."""
    permission_classes = (
        permissions.IsAuthenticated,
    )
    model = Invoice
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer
    pdf_template_name = 'billing/invoice_pdf.html'
    pdf_filename = 'invoice.pdf'
    throttle_scope = None

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('items')
        return queryset.filter(admin=self.request.user, status__gte=Invoice.STATUS_CHOICES.PAYMENT_SCHEDULED)

    @detail_route(methods=['get'], serializer_class=InvoicePdfSerializer)
    def pdf(self, request, *args, **kwargs):
        self.instance = self.get_object()
        serializer = self.get_serializer(self.instance)
        response = Response(serializer.data)
        request.accepted_renderer = PDFRenderer()
        request.accepted_media_type = PDFRenderer.media_type
        return response

    @detail_route(methods=['post'], serializer_class=Serializer, throttle_scope='invoice_retry_payment')
    def retry_payment(self, request, *args, **kwargs):
        invoice = self.get_object()
        if invoice.status != Invoice.STATUS_CHOICES.PAYMENT_FAILED:
            raise InvalidInvoiceStatus()

        charge_result = invoice.charge()
        if charge_result is not True:
            raise PaymentFailed(str(charge_result))
        return Response(InvoiceSerializer(invoice, context=self.get_serializer_context()).data)

    def get_pdf_template_context(self):
        if self.instance:
            return {
                'admin': self.instance.admin,
                'invoice': self.instance,
                'billing_profile': self.instance.admin.billing_profile,
            }


class CardViewSet(CreateStripeResourceMixin, RetrieveStripeResourceMixin,
                  UpdateStripeResourceMixin, DestroyStripeResourceMixin,
                  GenericStripeViewSet):
    """API endpoint for credit cards information"""

    permission_classes = (
        permissions.IsAuthenticated,
    )

    resource = stripe.Card
    serializer_class = StripeCardSerializer
    create_serializer_class = StripeTokenSerializer

    def get_customer(self):
        return self.request.user.billing_profile.customer

    def get_resource(self):
        return self.get_customer().sources

    def retrieve_resource(self, resource=None):
        if resource is None:
            resource = self.get_resource()

        params = self.filter_resource(resource)

        try:
            obj = resource.all(**params).data[0]
        except (IndexError, KeyError, stripe.StripeError):
            raise Http404('You don\'t have any card defined.')

        self.check_object_permissions(self.request, obj)
        return obj

    def create(self, request, *args, **kwargs):
        create_serializer = self.create_serializer_class(data=request.data)
        if not create_serializer.is_valid():
            return Response(create_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        token = create_serializer.data['token']
        try:
            card = self.get_resource().create(card=token)
        except stripe.CardError as ex:
            raise StripeCardError(str(ex))

        try:
            # We need to set this new card as default one
            customer = self.get_customer()
            customer.default_source = card.id
            customer.save()
        except stripe.StripeError as ex:
            raise StripeCardError(str(ex))

        serializer = self.serializer_class(card)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EventViewSet(AtomicMixin,
                   ViewSet):
    authentication_classes = ()
    permission_classes = ()

    def create(self, request):
        payload = json.loads(request.body)
        if Event.objects.filter(external_id=payload['id']).exists():
            logger.error('Duplicate event record: %s', payload['id'])
        else:
            Event.from_payload(payload)
        return Response()


class ProfileViewSet(AtomicMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     GenericViewSet):
    model = Profile
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = (
        permissions.IsAuthenticated,
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(admin=self.request.user)

    def get_object(self):
        queryset = self.get_queryset()
        obj = generics.get_object_or_404(queryset)
        self.check_object_permissions(self.request, obj)
        return obj


class SubscriptionViewSet(AtomicMixin,
                          ReadOnlyModelViewSet):
    model = Subscription
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer

    permission_classes = (
        permissions.IsAuthenticated,
    )

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.select_related('plan').filter(admin=self.request.user)
        # Filter out subscriptions that have already ended so we always get the current one on top of the list
        return qs.exclude(range__fully_lt=DateRange(date.today()))

    @detail_route(methods=['post'], serializer_class=Serializer)
    def cancel(self, request, *args, **kwargs):
        # Make a select for update lock on admin to make sure subscriptions are properly saved
        Admin.objects.select_for_update().get(pk=request.user.id)
        subscription = self.object = self.get_object()

        if not subscription.plan.paid_plan:
            raise CannotCancelUnpaidSubscription()

        # Subscription already got an end date, move along
        if subscription.end is not None:
            return Response(SubscriptionSerializer(subscription, context=self.get_serializer_context()).data)

        now = timezone.now()
        # Add grace period so we never ever cancel a plan that have an already partially calculated invoice
        now += timedelta(hours=settings.BILLING_GRACE_PERIOD_FOR_PLAN_CHANGING)
        now = now.date()

        # If it's the current or almost current subscription, then change the end to end of coming period
        if subscription.start <= now:
            subscription.range = DateRange(subscription.start, now + relativedelta(day=1, months=1))
            subscription.save()
            return Response(SubscriptionSerializer(subscription, context=self.get_serializer_context()).data)

        # Otherwise, just delete the subscription (it's the future one counting the grace period)
        subscription.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PricingPlanViewSet(AtomicMixin,
                         ReadOnlyModelViewSet):
    model = PricingPlan
    queryset = PricingPlan.objects.all()
    serializer_class = PricingPlanSerializer
    lookup_field = 'name'

    permission_classes = (
        permissions.AllowAny,
    )

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(available=True)

    @detail_route(methods=['post'],
                  serializer_class=PricingPlanSubscribeSerializer,
                  permission_classes=(permissions.IsAuthenticated,))
    def subscribe(self, request, *args, **kwargs):
        # Make a select for update lock on admin to make sure subscriptions are properly saved
        admin = Admin.objects.select_for_update().get(pk=request.user.id)
        plan = self.object = self.get_object()

        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            now = timezone.now()
            commitment = serializer.validated_data['commitment']

            try:
                current_subscription = Subscription.objects.select_related('plan').active_for_admin(admin_id=admin.id,
                                                                                                    now=now).get()
                is_paid_plan = current_subscription.plan.paid_plan
            except Subscription.DoesNotExist:
                current_subscription = None
                is_paid_plan = False

            start_date = now

            # Depending if current plan is paid one or not, there is a different logic on subscribing
            if is_paid_plan:
                # If current plan is a paid one, next subscription need to start on next billing cycle.
                start_date += timedelta(hours=settings.BILLING_GRACE_PERIOD_FOR_PLAN_CHANGING)
                start_date += relativedelta(day=1, months=+1)
                start_date = start_date.date()
                charged_until = start_date

                # If there is any - delete a subscription that's yet to start (it wasn't charged)
                Subscription.objects.filter(admin_id=admin.id, range__startswith=start_date).delete()

                # Check if last subscription is the same one as the one we want to subscribe to
                last_subscription = Subscription.objects.filter(admin=admin).last()
                if last_subscription.plan_id == plan.id and last_subscription.commitment == commitment:
                    last_subscription.range = DateRange(last_subscription.start, None)
                    last_subscription.save()
                    return Response(SubscriptionSerializer(last_subscription,
                                                           context=self.get_serializer_context()).data)
            else:
                # If current plan is a free one, start paid plan asap
                start_date = start_date.date()
                charged_until = start_date + relativedelta(day=1, months=+1)

                # Invalidate cached subscription as we are about to create a new one for current period
                Profile.invalidate_active_subscription(admin.id)

                # Calculate plan fee
                plan_fee = plan.get_plan_fee(commitment, start_date=start_date)
                # Charge invoice
                invoice = Invoice(admin=admin,
                                  plan_fee=plan_fee,
                                  period=start_date.replace(day=1),
                                  due_date=start_date + timedelta(days=settings.BILLING_DEFAULT_DUE_DATE),
                                  is_prorated=start_date.day != 1)
                invoice.save()
                charge_result = invoice.charge()

                InvoiceItem.objects.create(invoice=invoice,
                                           source=InvoiceItem.SOURCES.PLAN_FEE,
                                           quantity=1,
                                           price=plan_fee)

                # If charge failed, reverse everything done here, no paid plan for you!
                if charge_result is not True:
                    raise PaymentFailed(str(charge_result))

            # Finish current subscription
            if current_subscription:
                current_subscription.range = DateRange(current_subscription.start, start_date)
                current_subscription.save()

            # Finally create subscription
            subscription = Subscription.objects.create(range=DateRange(start_date, None),
                                                       commitment=commitment,
                                                       admin=admin,
                                                       charged_until=charged_until,
                                                       plan=plan)

            return Response(SubscriptionSerializer(subscription, context=self.get_serializer_context()).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
