# coding=UTF8
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django_atomic_signals import post_exit_atomic_block, pre_enter_atomic_block

from apps.core.abstract_models import AclAbstractModel, CacheableAbstractModel, LiveAbstractModel
from apps.core.helpers import (
    add_post_transaction_success_operation,
    get_last_transaction_block_list,
    get_transaction_blocks_list
)
from apps.core.signals import post_soft_delete
from apps.core.tasks import DeleteLiveObjectTask
from apps.instances.helpers import get_current_instance, is_model_in_tenant_apps


@receiver(pre_enter_atomic_block, dispatch_uid='add_transaction_block')
def add_transaction_block(using, outermost, savepoint, **kwargs):
    get_transaction_blocks_list(using).append([])


@receiver(post_exit_atomic_block, dispatch_uid='process_transaction_operation_block')
def process_transaction_operation_block(using, outermost, savepoint, successful, **kwargs):
    transaction_block_operations = get_transaction_blocks_list(using).pop()

    for operation in transaction_block_operations:
        on_success, func, f_args, f_kwargs = operation
        if on_success == successful or on_success is None:
            if not outermost and successful:
                # if we're not yet in outermost transaction but it is a successful one
                # queue and see if transaction that wraps this one will fail
                get_last_transaction_block_list(using).append(operation)
            else:
                # otherwise just run the queued function
                func(*f_args, **f_kwargs)


@receiver(post_save, dispatch_uid='cacheablemodel_post_save_handler')
def cacheablemodel_post_save_handler(sender, instance, created, **kwargs):
    if isinstance(instance, CacheableAbstractModel) and not created:
        instance.invalidate_cache()


@receiver(post_delete, dispatch_uid='cacheablemodel_post_delete_handler')
def cacheablemodel_post_delete_handler(sender, instance, **kwargs):
    if isinstance(instance, CacheableAbstractModel) and (not isinstance(instance, LiveAbstractModel) or
                                                         instance._is_live):
        # No need to invalidate live object that was marked as dead as it was invalidated
        # after soft delete (which calls post_save)
        instance.invalidate_cache()


@receiver(post_soft_delete, dispatch_uid='livemodel_post_soft_delete_handler')
def livemodel_post_soft_delete_handler(sender, instance, using, **kwargs):
    sender_meta = sender._meta
    instance_pk = None
    if is_model_in_tenant_apps(sender):
        instance_pk = get_current_instance().pk

    # queue actual cleanup job
    add_post_transaction_success_operation(DeleteLiveObjectTask.delay,
                                           using=using,
                                           model_class_name='%s.%s' % (sender_meta.app_label, sender_meta.model_name),
                                           object_pk=instance.pk,
                                           instance_pk=instance_pk)


@receiver(pre_save, dispatch_uid='aclmodel_pre_save_handler')
def aclmodel_pre_save_handler(sender, instance, update_fields, **kwargs):
    if isinstance(instance, AclAbstractModel) and (not update_fields or 'acl' in update_fields):
        acl = instance.acl or {}
        # setup _users, _groups and _public permissions per object
        # after cleanup: as "read" is a minimum permission to be specified,
        # we can assume that if acl definition exists, "read" is set as well
        instance._users = sorted(map(int, acl['users'].keys()) if 'users' in acl else [])
        instance._groups = sorted(map(int, acl['groups'].keys()) if 'groups' in acl else [])
        instance._public = '*' in acl
