# coding=UTF8
from django.dispatch import Signal

social_user_created = Signal(providing_args=['view', 'instance'])
