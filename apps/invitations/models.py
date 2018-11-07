# coding=UTF8
from django.db import models

from apps.admins.models import Admin, Role
from apps.core.abstract_models import UniqueKeyAbstractModel
from apps.core.fields import LowercaseEmailField
from apps.core.helpers import MetaIntEnum
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS


class Invitation(UniqueKeyAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'full': FULL_PERMISSIONS,
            'write': {API_PERMISSIONS.READ},
            'read': {API_PERMISSIONS.READ},
        }
    }

    class STATE_CHOICES(MetaIntEnum):
        NEW = 1, 'new'
        DECLINED = 2, 'declined'
        ACCEPTED = 3, 'accepted'

    state = models.SmallIntegerField(choices=STATE_CHOICES.as_choices(), default=STATE_CHOICES.NEW)
    instance = models.ForeignKey('instances.Instance', on_delete=models.CASCADE)
    admin = models.ForeignKey(Admin, on_delete=models.SET_NULL, default=None, blank=True, null=True)
    email = LowercaseEmailField(max_length=254)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    inviter = models.ForeignKey(Admin, related_name='sent_invitations', null=True, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('id',)
        unique_together = ('email', 'instance',)

    def __str__(self):
        return 'Invitation[id=%s, email=%s, admin_id=%s, role=%s]' % (self.id, self.email, self.admin_id, self.role_id)

    def accept(self, admin):
        self.admin = admin
        self.state = self.STATE_CHOICES.ACCEPTED
        self.save()
        admin.add_to_instance(instance=self.instance, role_name=self.role.name)
