# coding=UTF8
from rest_framework.permissions import BasePermission

from apps.billing.exceptions import AdminStatusException
from apps.billing.models import Profile


class AdminInGoodStanding(BasePermission):

    @staticmethod
    def check_admin(admin_id):
        status = Profile.get_billing_status(admin_id)
        if status is not None:
            raise AdminStatusException(detail=status.verbose, status=str(status))
        return True

    def has_permission(self, request, view):
        if request.user.is_authenticated:
            return self.check_admin(request.user.id)
        else:
            return True


class OwnerInGoodStanding(AdminInGoodStanding):
    """
    Checks if instance owner hasn't reached hard limit, has subscription active.

    403 is raised by permission checker when this method returns False.
    """

    def has_permission(self, request, view):
        if request.user.is_staff:
            return True
        return self.check_admin(request.instance.owner_id)

    @staticmethod
    def is_admin_in_good_standing(admin_id):
        return Profile.get_billing_status(admin_id) is None
