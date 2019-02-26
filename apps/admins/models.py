# coding=UTF8
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import models
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import ugettext_lazy as _

from apps.admins.managers import AdminManager
from apps.core.abstract_models import (
    CacheableAbstractModel,
    LiveAbstractModel,
    MetadataAbstractModel,
    TrackChangesAbstractModel,
    UniqueKeyAbstractModel
)
from apps.core.fields import LowercaseEmailField
from apps.core.helpers import Cached, MetaIntEnum, add_post_transaction_success_operation, generate_key
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS


class Role(CacheableAbstractModel):
    OWNER_ROLE = 'owner'

    class ROLE_CHOICES(MetaIntEnum):
        FULL = 1, 'full'
        WRITE = 2, 'write'
        READ = 3, 'read'

    ROLE_HIERARCHY = (OWNER_ROLE, ROLE_CHOICES.FULL.verbose, ROLE_CHOICES.WRITE.verbose, ROLE_CHOICES.READ.verbose)

    name = models.CharField('name', max_length=64, unique=True, choices=ROLE_CHOICES.as_choices())

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'Role[name=%s]' % self.name


class Admin(CacheableAbstractModel, MetadataAbstractModel, LiveAbstractModel, TrackChangesAbstractModel,
            UniqueKeyAbstractModel, AbstractBaseUser):
    SYNC_INVALIDATION = True
    USERNAME_FIELD = 'email'
    KEY_FIELD_KWARGS = {}

    email = LowercaseEmailField('email address', max_length=254)

    first_name = models.CharField(_('first name'), max_length=64, blank=True)
    last_name = models.CharField(_('last name'), max_length=64, blank=True)
    is_staff = models.BooleanField(_('staff status'), default=False,
                                   help_text=_('Designates whether the user can log into this admin '
                                               'site.'))
    is_active = models.BooleanField(_('active'), default=False,
                                    help_text=_('Designates whether this user should be treated as '
                                                'active. Unselect this instead of deleting accounts.'))
    is_superuser = models.BooleanField(_('superuser status'), default=False,
                                       help_text=_('Designates that this user has all permissions without '
                                                   'explicitly assigning them.'))
    is_trusted = models.BooleanField('trusted status', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    last_access = models.DateTimeField(auto_now_add=True)
    noticed_at = models.DateTimeField(null=True)  # deletion notice time

    objects = AdminManager()
    all_objects = AdminManager(include_soft_deleted=True)

    class Meta:
        ordering = ('id',)
        unique_together = ('email', '_is_live')

    def __str__(self):
        return 'Admin[id=%s, email=%s]' % (self.id, self.email)

    def generate_key(self):
        return generate_key(parity=True)

    def get_role_name(self, instance):
        if self.is_staff or instance.owner_id == self.id:
            return Role.OWNER_ROLE
        role_id = self.get_instance_role(instance=instance).role_id
        return Cached(Role, kwargs=dict(id=role_id)).get().name

    def is_role_satisfied(self, instance, role_name):
        """
        Returns true if passed role_name is satisfied in an instance.
        Respects role hierarchy so that e.g. is_role_satisfied(read) is satisfied when actual role is write or full.
        """
        try:
            instance_role_name = self.get_role_name(instance)
            return Role.ROLE_HIERARCHY.index(instance_role_name) <= Role.ROLE_HIERARCHY.index(role_name)
        except AdminInstanceRole.DoesNotExist:
            return False

    def get_instance_role(self, instance):
        return Cached(AdminInstanceRole, kwargs=dict(instance=instance.id, admin=self.id)).get()

    def get_full_name(self):
        """
        Returns the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        """Returns the short name for the user."""
        return self.first_name

    def remove_from_instance(self, instance):
        role = AdminInstanceRole.objects.get(instance=instance, admin=self)
        role.delete()

    def add_to_instance(self, instance, role_name='full'):
        role_id = Role.ROLE_CHOICES(role_name).value
        try:
            admin_instance_role = AdminInstanceRole.objects.filter(admin=self, instance=instance).get()
            admin_instance_role_name = Role.ROLE_CHOICES(admin_instance_role.role_id).verbose

            if Role.ROLE_HIERARCHY.index(admin_instance_role_name) > Role.ROLE_HIERARCHY.index(role_name):
                admin_instance_role.role_id = role_id
                admin_instance_role.save()
            return admin_instance_role
        except AdminInstanceRole.DoesNotExist:
            return AdminInstanceRole.objects.create(role_id=role_id, admin=self, instance=instance)

    def instances(self):
        from apps.instances.models import Instance

        return Instance.objects.filter(admin_roles__admin=self)

    def update_last_access(self, save=True):
        """
        Returns True if last_access was older then 12 hour and set to new value.
        Returns False if last_access is younger then 12 hour and does not need updating.
        """

        now = timezone.now()
        if self.last_access + timedelta(hours=12) < now:
            self.last_access = now
            self.noticed_at = None
            if save:
                self.save(update_fields=['last_access', 'noticed_at'])
            return True
        return False

    def send_activation_email(self, token_generator):
        from apps.analytics.tasks import NotifyAboutResendAdminActivationEmail

        token = token_generator.make_token(self)
        uid = urlsafe_base64_encode(force_bytes(self.pk)).decode()
        context = {
            'admin_id': self.id,
            'uid': uid,
            'token': token,
        }
        add_post_transaction_success_operation(
            NotifyAboutResendAdminActivationEmail.delay,
            **context
        )


class AnonymousAdmin(AnonymousUser):
    pass


class SocialProfile(models.Model):
    class BACKENDS(MetaIntEnum):
        FACEBOOK = 0, 'facebook'
        GOOGLE_OAUTH2 = 1, 'google-oauth2'
        GITHUB = 2, 'github'
        LINKEDIN = 3, 'linkedin'
        TWITTER = 4, 'twitter'

    backend = models.SmallIntegerField(choices=BACKENDS.as_choices())
    social_id = models.CharField(max_length=32)

    class Meta:
        ordering = ('id',)
        abstract = True
        unique_together = ('backend', 'social_id')


class AdminSocialProfile(SocialProfile):
    admin = models.ForeignKey(Admin, related_name='social_profiles', on_delete=models.CASCADE)


class AdminInstanceRole(CacheableAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'full': FULL_PERMISSIONS,
            'write': {API_PERMISSIONS.READ},
            'read': {API_PERMISSIONS.READ},
        }
    }

    admin = models.ForeignKey(Admin, related_name='instance_roles', on_delete=models.CASCADE)
    instance = models.ForeignKey('instances.Instance', related_name='admin_roles', on_delete=models.CASCADE)
    role = models.ForeignKey(Role, related_name='instance_admins', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('admin', 'instance',)
        ordering = ('id',)

    def __str__(self):
        return 'AdminInstanceRole[id=%s, admin_id=%s, instance_id=%s]' % (self.id, self.admin_id, self.instance_id)
