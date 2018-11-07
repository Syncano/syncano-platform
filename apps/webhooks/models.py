from django.db import models

from apps.codeboxes.models import CodeBox, Trace
from apps.core.abstract_models import (
    AclAbstractModel,
    CacheableAbstractModel,
    DescriptionAbstractModel,
    UniqueKeyAbstractModel
)
from apps.core.fields import StrippedSlugField
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS, Permission
from apps.redis_storage import fields as redis_fields


class Webhook(AclAbstractModel, CacheableAbstractModel, DescriptionAbstractModel, UniqueKeyAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    # v2 permission config
    ENDPOINT_ACTIONS = ('endpoint_get', 'endpoint_put',
                        'endpoint_patch', 'endpoint_post',
                        'endpoint_delete',)
    RUN_PERMISSION = Permission('run', actions=ENDPOINT_ACTIONS)
    OBJECT_ACL_PERMISSIONS = (
        AclAbstractModel.READ_PERMISSION,
        RUN_PERMISSION,
    )

    GET_PERMISSION = Permission('get', actions=('retrieve',) + ENDPOINT_ACTIONS)
    ENDPOINT_ACL_PERMISSIONS = (
        GET_PERMISSION,
        AclAbstractModel.LIST_PERMISSION,
    )

    KEY_FIELD_NAME = 'public_link'
    KEY_FIELD_KWARGS = {'unique': True}

    name = StrippedSlugField(max_length=64, unique=True)
    codebox = models.ForeignKey(CodeBox, on_delete=models.CASCADE)
    public = models.BooleanField(default=False)
    socket = models.ForeignKey('sockets.Socket', blank=True, null=True, default=None, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Script Endpoint'
        ordering = ('id',)
        index_together = ('public_link', 'public')

    def __str__(self):
        return 'Webhook[name=%s, codebox_id=%d]' % (self.name, self.codebox_id)


class WebhookTrace(Trace):
    list_template_args = '{webhook.id}'

    meta = redis_fields.JSONField(default={})
    args = redis_fields.JSONField(default={})
