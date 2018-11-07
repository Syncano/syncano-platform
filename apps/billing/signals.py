# coding=UTF8
from django.dispatch import Signal

event_validation_error = Signal(providing_args=['data', 'exception'])

EVENT_SIGNALS = {hook: Signal(providing_args=['event']) for hook in [
    'account.updated',
    'account.application.deauthorized',
    'application_fee.created',
    'application_fee.refunded',
    'balance.available',
    'charge.succeeded',
    'charge.failed',
    'charge.refunded',
    'charge.captured',
    'charge.updated',
    'charge.updated',
    'charge.dispute.created',
    'charge.dispute.updated',
    'charge.dispute.closed',
    'charge.dispute.funds_withdrawn',
    'charge.dispute.funds_reinstated',
    'customer.created',
    'customer.updated',
    'customer.deleted',
    'customer.card.created',
    'customer.card.updated',
    'customer.card.deleted',
    'customer.subscription.created',
    'customer.subscription.updated',
    'customer.subscription.deleted',
    'customer.subscription.trial_will_end',
    'customer.discount.created',
    'customer.discount.updated',
    'customer.discount.deleted',
    'invoice.created',
    'invoice.updated',
    'invoice.payment_succeeded',
    'invoice.payment_failed',
    'invoiceitem.created',
    'invoiceitem.updated',
    'invoiceitem.deleted',
    'plan.created',
    'plan.updated',
    'plan.deleted',
    'coupon.created',
    'coupon.updated',
    'coupon.deleted',
    'recipient.created',
    'recipient.updated',
    'recipient.deleted',
    'transfer.created',
    'transfer.updated',
    'transfer.reversed',
    'transfer.paid',
    'transfer.failed',
    'bitcoin.receiver.created',
    'bitcoin.receiver.transaction.created',
    'bitcoin.receiver.filled',
    'ping',
]}
