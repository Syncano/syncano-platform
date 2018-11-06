# coding=UTF8
from django.dispatch import receiver

from apps.core.signals import post_tenant_migrate
from apps.response_templates.predefined_templates import PredefinedTemplates


# Response templates signal handlers
@receiver(post_tenant_migrate, dispatch_uid='create_response_templates_after_tenant_migrate')
def create_response_templates_after_tenant_migrate(sender, tenant, created, partial, **kwargs):
    if created:
        PredefinedTemplates.create_template_responses(check=partial)
