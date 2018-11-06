import stripe
from rest_framework import serializers

from apps.billing.exceptions import AdminStatusException
from apps.billing.permissions import AdminInGoodStanding
from apps.core.field_serializers import DisplayedChoiceField, JSONField, LowercaseChoiceField
from apps.core.mixins.serializers import CleanValidateMixin, DynamicFieldsMixin, HyperlinkedMixin
from apps.instances.v1.serializers import InstanceSerializer

from .models import AdminLimit, Coupon, Discount, Invoice, InvoiceItem, PricingPlan, Profile, Subscription


class CouponSerializer(DynamicFieldsMixin, HyperlinkedMixin, serializers.ModelSerializer):
    lookup_field = 'name'
    hyperlinks = (
        ('self', 'coupon-detail', ('pk',)),
        ('redeem', 'discount-list', None),
    )

    currency = LowercaseChoiceField(Coupon.CURRENCY_CHOICES)

    class Meta:
        model = Coupon
        fields = ('name', 'amount_off', 'percent_off', 'currency',
                  'duration', 'redeem_by')
        required_fields = ('name', 'redeem_by', 'duration',)

    def to_internal_value(self, data):
        """In `percent_off` and `amount_off` pairs, one should be optional,

        We restore field by providing it a default `0` value.
        """
        reverted_data = super().to_internal_value(data)

        if reverted_data is not None:
            if 'percent_off' not in reverted_data:
                reverted_data['percent_off'] = 0
            if 'amount_off' not in reverted_data:
                reverted_data['amount_off'] = 0

        return reverted_data

    def validate_duration(self, value):
        if value < 1:
            raise serializers.ValidationError("Duration has to be at least one month.")
        return value

    def validate(self, data):
        """
        Check constraints for `percent_off`, `amount_off` pair.
        """
        if data['percent_off'] == 0 and data['amount_off'] == 0:
            raise serializers.ValidationError("Either `percent_off` or `amount_off`"
                                              " can't be 0.")
        if data['percent_off'] != 0 and data['amount_off'] != 0:
            raise serializers.ValidationError("Coupon can be either for fixed amount of money"
                                              " or for percent off, not both.")
        return super().validate(data)


class CouponRedemptionSerializer(HyperlinkedMixin, serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'discount-detail', ('pk',)),
    )

    class Meta:
        model = Discount
        fields = ('coupon', 'instance')
        extra_kwargs = {'customer': {'write_only': True}}

    def get_fields(self):
        """Get fields for example for django rest framework generated forms"""
        fields = super().get_fields()

        # user can only choose from his instances
        if 'view' in self.context:
            fields['instance'].queryset = self.context['view'].request.user.instances()
        return fields

    def from_native(self, data, files):
        """We don't want to create an instance of the object in this serializer"""
        return None


class DiscountSerializer(DynamicFieldsMixin, HyperlinkedMixin, CleanValidateMixin, serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'discount-detail', ('pk',)),
    )

    coupon = CouponSerializer()
    instance = InstanceSerializer()

    class Meta:
        model = Discount
        fields = ('id', 'coupon', 'instance', 'start', 'end')
        extra_kwargs = {
            'customer': {'write_only': True},
            'start': {'read_only': True},
            'end': {'read_only': True}
        }


class StripeSerializer(serializers.Serializer):
    """A serializer that deals with Stripe resources."""

    def create(self, validated_data):
        # In Stripe empty value means None.
        attrs = {k: v or None for k, v in validated_data.items()}
        instance = self.Meta.resource.construct_from(attrs, self.Meta.api_key)
        return self.Meta.resource.create(**instance)

    def update(self, instance, validated_data):
        # In Stripe empty value means None.
        for k, v in validated_data.items():
            instance[k] = v or None
        instance.save()
        return instance


class StripeTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class StripeCardSerializer(DynamicFieldsMixin, HyperlinkedMixin, StripeSerializer):
    hyperlinks = (
        ('self', 'billing-card', ()),
    )

    id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=200, required=False, label='Cardholder name')
    brand = serializers.CharField(read_only=True)
    exp_month = serializers.IntegerField(read_only=True)
    exp_year = serializers.IntegerField(read_only=True)
    fingerprint = serializers.CharField(read_only=True)
    funding = serializers.CharField(read_only=True)
    last4 = serializers.CharField(read_only=True)
    dynamic_last4 = serializers.CharField(read_only=True)
    address_zip = serializers.CharField(max_length=200, required=False)
    address_state = serializers.CharField(max_length=200, required=False)
    address_country = serializers.CharField(max_length=200, required=False)
    address_line2 = serializers.CharField(max_length=200, required=False)
    address_line1 = serializers.CharField(max_length=200, required=False)
    address_city = serializers.CharField(max_length=200, required=False)
    address_line1_check = serializers.CharField(read_only=True)
    address_zip_check = serializers.CharField(read_only=True)
    country = serializers.CharField(read_only=True)
    cvc_check = serializers.CharField(read_only=True)

    class Meta:
        resource = stripe.Card


class BalanceItemSerializer(serializers.Serializer):
    amount = serializers.CharField(source='formatted_amount')
    quantity = serializers.IntegerField()
    source = DisplayedChoiceField(choices=InvoiceItem.SOURCES.as_choices())


class InvoiceItemSerializer(BalanceItemSerializer):
    instance_name = serializers.CharField()
    price = serializers.CharField(source='formatted_price')

    def to_native(self, item):
        source = item.source
        serialized = super().to_native(item)
        if source == InvoiceItem.SOURCES.PLAN_FEE:
            serialized.pop('price')
            serialized.pop('instance_name')
        return serialized


class InvoiceSerializer(DynamicFieldsMixin, HyperlinkedMixin, serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'invoice-detail', ('pk',)),
        ('pdf', 'invoice-pdf', ('pk',)),
        ('retry-payment', 'invoice-retry-payment', ('pk',)),
    )

    period = serializers.CharField(source='formatted_period')
    amount = serializers.CharField(source='formatted_amount')
    items = InvoiceItemSerializer(many=True)
    status = DisplayedChoiceField(choices=Invoice.STATUS_CHOICES.as_choices())

    class Meta:
        model = Invoice
        fields = ('id', 'period', 'amount', 'status', 'created_at', 'updated_at', 'items')


class InvoiceItemPdfSerializer(InvoiceItemSerializer):
    quantity = serializers.CharField(source='formatted_quantity')


class InvoicePdfSerializer(InvoiceSerializer):
    items = InvoiceItemPdfSerializer(many=True)


class PricingPlanSerializer(DynamicFieldsMixin, HyperlinkedMixin, serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'plan-detail', ('name',)),
        ('subscribe', 'plan-subscribe', ('name',)),
    )
    pricing = JSONField()
    options = JSONField()

    class Meta:
        model = PricingPlan
        fields = ('name', 'pricing', 'options')


class SubscriptionSerializer(DynamicFieldsMixin, HyperlinkedMixin, serializers.ModelSerializer):
    hyperlinks = (
        ('self', 'subscription-detail', ('id',)),
        ('cancel', 'subscription-cancel', ('id',)),
    )
    plan = serializers.CharField(source='plan.name')
    pricing = serializers.SerializerMethodField()
    commitment = JSONField(default={})
    start = serializers.DateField()
    end = serializers.DateField()

    class Meta:
        model = Subscription
        fields = ('id', 'start', 'end', 'plan', 'commitment', 'pricing',)

    def get_pricing(self, obj):
        pricing = {}
        commitment = obj.commitment
        for key, value in commitment.items():
            pricing[key] = obj.plan.pricing[key][value]
        return pricing


class AdminLimitSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    LIMITS_INCLUDED = ('instances_count',)

    class Meta:
        model = AdminLimit
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for limit_field in self.LIMITS_INCLUDED:
            if limit_field not in self.fields:
                self.fields[limit_field] = serializers.IntegerField(source='get_%s' % limit_field)


class AdminInstanceLimitSerializer(AdminLimitSerializer):
    LIMITS_INCLUDED = ('storage', 'rate', 'codebox_concurrency', 'classes_count',)


class ProfileSerializer(DynamicFieldsMixin, CleanValidateMixin, serializers.ModelSerializer):
    balance = BalanceItemSerializer(many=True, read_only=True)
    subscription = SubscriptionSerializer(source='current_subscription', read_only=True)
    failed_invoice = InvoiceSerializer(read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ('balance', 'subscription', 'hard_limit', 'soft_limit', 'company_name', 'first_name',
                  'last_name', 'address_line1', 'address_line2', 'address_city', 'address_state',
                  'address_zip', 'address_country', 'tax_number', 'failed_invoice',
                  'status')

    def get_status(self, obj):
        try:
            AdminInGoodStanding.check_admin(obj.admin_id)
        except AdminStatusException as ex:
            return ex.status
        return 'ok'


class PricingPlanSubscribeSerializer(serializers.Serializer):
    commitment = JSONField()

    def validate_commitment(self, value):
        if not value:
            return value

        commitment = value
        plan = self.context['view'].object
        options = plan.options

        if not isinstance(commitment, dict):
            raise serializers.ValidationError(
                'Not a valid value type. Specify it in a form of JSON object, e.g. {"api": 20, "cbx": 5}.')
        if len(commitment) != len(options):
            raise serializers.ValidationError(
                'You need to specify all of plan\'s options. '
                'Expected: {num}, got {keys}.'.format(num=len(options), keys=len(commitment)))

        for key, val in commitment.items():
            if key not in options:
                raise serializers.ValidationError(
                    'Invalid key: {key}. '
                    'Does not match any key in plan\'s options.'.format(key=key))
            if val not in options[key]:
                raise serializers.ValidationError(
                    'Invalid value: {value} for key "{key}". '
                    'Not a valid option for selected plan.'.format(value=val, key=key))
        return value
