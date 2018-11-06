# coding=UTF8
from apps.core.querysets import CountEstimateLiveQuerySet


class KlassQuerySet(CountEstimateLiveQuerySet):
    def include_object_count(self, real_limit=1000):
        alias = self.query.table_map.get(self.query.base_table)[0]
        query = "'SELECT id FROM data_dataobject WHERE _klass_id=' || \"{alias}\".\"id\"".format(
            alias=alias
        )
        return self.add_count_estimate('_objects_count', query, real_limit=real_limit, raw=True)
