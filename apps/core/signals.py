# coding=UTF8
from django.db.models.signals import ModelSignal
from django.dispatch import Signal

pre_soft_delete = ModelSignal(providing_args=['instance', 'using'], use_caching=True)
post_soft_delete = ModelSignal(providing_args=['instance', 'using'], use_caching=True)

pre_tenant_migrate = Signal(providing_args=['tenant', 'verbosity', 'using'])
post_tenant_migrate = Signal(providing_args=['tenant', 'verbosity', 'using', 'created', 'partial'])
post_full_migrate = Signal(providing_args=['verbosity', 'using'])

apiview_view_processed = Signal(providing_args=['view', 'instance', 'action'])
apiview_finalize_response = Signal(providing_args=['view', 'request', 'response'])
