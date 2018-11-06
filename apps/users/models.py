# coding=UTF8
from django.contrib.auth.hashers import check_password, make_password
from django.db import models

from apps.admins.models import SocialProfile
from apps.core.abstract_models import (
    AclAbstractBaseModel,
    AclAbstractModel,
    CacheableAbstractModel,
    LabelDescriptionAbstractModel,
    LiveAbstractModel,
    TrackChangesAbstractModel,
    UniqueKeyAbstractModel
)
from apps.core.decorators import cached
from apps.core.fields import LowercaseCharField, StrippedSlugField
from apps.core.helpers import generate_key
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS, Permission
from apps.data.models import DataObject


class Group(AclAbstractModel, LabelDescriptionAbstractModel, LiveAbstractModel, TrackChangesAbstractModel):
    # v1 permission config
    PERMISSION_CONFIG = {
        'api_key': {API_PERMISSIONS.READ},
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    # v2 permission config
    ADD_USER_PERMISSIONS = Permission('add_user')
    REMOVE_USER_PERMISSIONS = Permission('remove_user')

    OBJECT_ACL_PERMISSIONS = AclAbstractModel.OBJECT_ACL_PERMISSIONS + (
        ADD_USER_PERMISSIONS,
        REMOVE_USER_PERMISSIONS,
    )

    name = StrippedSlugField(max_length=64, null=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ('id',)
        unique_together = ('name', '_is_live')

    def __str__(self):
        return 'Group[id=%s, name=%s]' % (self.id, self.name)


class Membership(models.Model):
    PERMISSION_CONFIG = {
        'api_key': {API_PERMISSIONS.READ},
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    user = models.ForeignKey('User', on_delete=models.CASCADE)
    group = models.ForeignKey('Group', on_delete=models.CASCADE)

    class Meta:
        ordering = ('id',)
        unique_together = ('user', 'group')


class User(AclAbstractBaseModel, CacheableAbstractModel, LiveAbstractModel, TrackChangesAbstractModel,
           UniqueKeyAbstractModel):
    # v1 permission fields
    PERMISSION_CONFIG = {
        'api_key': {API_PERMISSIONS.READ, API_PERMISSIONS.UPDATE},
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    # v2 permission config
    WRITE_PERMISSION = Permission('write', actions=('update', 'partial_update', 'destroy', 'reset_key'))
    OBJECT_ACL_PERMISSIONS = (
        DataObject.READ_PERMISSION,
        WRITE_PERMISSION,
    )

    UPDATE_PERMISSION = Permission('update', actions=('update', 'partial_update', 'reset_key'))
    ENDPOINT_ACL_PERMISSIONS = (
        DataObject.GET_PERMISSION,
        DataObject.LIST_PERMISSION,
        DataObject.CREATE_PERMISSION,
        UPDATE_PERMISSION,
        DataObject.DELETE_PERMISSION,
    )

    KEY_FIELD_KWARGS = {}

    username = LowercaseCharField(max_length=64, db_index=True)
    password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    groups = models.ManyToManyField('Group', through='Membership')

    class Meta:
        ordering = ('id',)
        unique_together = ('username', '_is_live')

    def __init__(self, *args, **kwargs):
        self.profile_data = kwargs.pop('profile_data', None)
        super().__init__(*args, **kwargs)

    def __str__(self):
        return 'User[id=%s, username=%s]' % (self.id, self.username)

    def generate_key(self):
        return generate_key(parity=True)

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        """
        Returns a boolean of whether the raw_password was correct. Handles
        hashing formats behind the scenes.
        """

        def setter(raw_password):
            self.set_password(raw_password)
            self.save(update_fields=["password"])

        return check_password(raw_password, self.password, setter)

    @staticmethod
    @cached()
    def get_group_ids_for_user(user_id):
        return list(Membership.objects.filter(user=user_id).values_list('group_id', flat=True))

    def get_group_ids(self):
        return self.get_group_ids_for_user(self.id)


class UserSocialProfile(SocialProfile):
    user = models.ForeignKey(User, related_name='social_profiles', on_delete=models.CASCADE)

    class Meta(SocialProfile.Meta):
        verbose_name = 'User Social Profile'
