# coding=UTF8
from apps.billing.models import AdminLimit
from apps.instances.throttling import InstanceRateThrottle


class ChannelPollRateThrottle(InstanceRateThrottle):
    def get_instance_rate(self, request, view):
        return AdminLimit.get_for_admin(request.instance.owner_id).get_poll_rate()
