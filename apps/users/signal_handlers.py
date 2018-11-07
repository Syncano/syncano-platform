# coding=UTF8

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.signals import post_tenant_migrate
from apps.data.models import DataObject, Klass
from apps.users.models import Membership, User


@receiver(post_tenant_migrate, dispatch_uid='create_user_profile_after_tenant_migrate')
def create_user_profile_after_tenant_migrate(sender, tenant, created, partial, **kwargs):
    klass_props = {
        'description': 'Class that holds profiles for users.',
        'visible': False
    }
    if not created:
        return

    if partial:
        Klass.objects.get_or_create(name=Klass.USER_PROFILE_NAME, defaults=klass_props)
    else:
        Klass.objects.create(name=Klass.USER_PROFILE_NAME, **klass_props)


@receiver(post_save, sender=User, dispatch_uid='user_post_save_handler')
def user_post_save_handler(sender, instance, created, **kwargs):
    profile_data = instance.profile_data
    if profile_data is False:
        # Allow explicitly disabling automatic profile creation
        return

    user_profile_klass = Klass.get_user_profile()
    profile_data = profile_data or {}
    profile_data.pop('owner', None)

    # Add default ACL
    if 'acl' not in profile_data:
        profile_data['acl'] = {}
    if 'users' not in profile_data['acl']:
        profile_data['acl']['users'] = {}

    profile_data['acl']['users'].update({str(instance.id): DataObject.get_acl_permission_values()[:]})
    if created:
        DataObject.load_klass(user_profile_klass)
        profile_data['_klass'] = user_profile_klass
        instance.profile = DataObject(owner=instance, **profile_data)
        instance.profile.save()


@receiver(post_save, sender=Membership, dispatch_uid='membership_post_save_handler')
@receiver(post_delete, sender=Membership, dispatch_uid='membership_post_delete_handler')
def membership_invalidate_handler(sender, instance, **kwargs):
    User.get_group_ids_for_user.invalidate(args=(instance.user_id,), immediate=False)


@receiver(post_save, sender=User, dispatch_uid='user_post_save_changes')
def user_post_save_changes(sender, instance, created, **kwargs):
    changes = None
    if not created:
        changes = instance.whats_changed()
    instance.changes = changes
