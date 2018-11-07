# coding=UTF8
from django.db import connections

from apps.core.helpers import get_count_estimate_from_query


class LiveQuerySetMixin:
    def soft_delete(self):
        self.update(_is_live=False)

    def live(self):
        return self.filter(_is_live=True)

    def dead(self):
        return self.filter(_is_live__isnull=True)


class CountEstimateQuerySetMixin:
    def add_count_estimate(self, param, sql, params=None, real_limit=1000, raw=False):
        cursor = connections[self.db].cursor()
        sql = cursor.mogrify(sql, params)
        if not raw:
            sql = sql.replace("'", "''")
        return self.extra(select={param: b"count_estimate(%s, %d)" % (sql, real_limit)})

    def count_estimate(self, real_limit=1000):
        return get_count_estimate_from_query(self.query, using=self.db, real_limit=real_limit)
