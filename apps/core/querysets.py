# coding=UTF8
from django.db.models import Q, query

from apps.core.mixins.querysets import CountEstimateQuerySetMixin, LiveQuerySetMixin


class LiveQuerySet(LiveQuerySetMixin, query.QuerySet):
    pass


class CountEstimateQuerySet(CountEstimateQuerySetMixin, query.QuerySet):
    pass


class CountEstimateLiveQuerySet(LiveQuerySetMixin, CountEstimateQuerySetMixin, query.QuerySet):
    pass


class AclQuerySet(query.QuerySet):
    def filter_acl(self, request):
        if request.auth and not request.auth.ignore_acl:
            qq = Q(_public=True)

            if request.auth_user:
                user_id = request.auth_user.id
                qq |= Q(_users__contains=[user_id])

                group_ids = request.auth_user.get_group_ids()
                if group_ids:
                    qq |= Q(_groups__overlap=group_ids)
                return self.filter(qq)
            return self.filter(_public=True)
        return self
