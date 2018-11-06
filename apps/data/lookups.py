# coding=UTF8
from django.contrib.gis.db.models.lookups import DWithinLookup
from django.contrib.postgres.lookups import DataContains, Overlap
from django.db.models import Field, lookups


@Field.register_lookup
class Like(lookups.PatternLookup):
    lookup_name = 'like'
    operator = 'LIKE %s'

    def get_rhs_op(self, connection, rhs):
        return self.operator % rhs


@Field.register_lookup
class ILike(Like):
    lookup_name = 'ilike'
    operator = 'ILIKE %s'


def create_lookup(lookups_dict, lookup, base_class, default_lookup_class=None):
    if default_lookup_class is None:
        default_lookup_class = Field.class_lookups[lookup]

    class HStoreLookup(base_class, default_lookup_class):
        pass

    lookups_dict[lookup] = HStoreLookup


hstore_lookups = {}


class HStoreLookupBase:
    def process_lhs(self, qn, connection, lhs=None):
        lhs = lhs or self.lhs
        output_field = lhs.output_field
        return output_field.db_field(qn, connection, lhs), []


for lookup in ('gt', 'gte', 'lt', 'lte', 'in', 'exact',
               'contains', 'startswith', 'endswith',
               'iexact', 'icontains', 'istartswith', 'iendswith', 'like', 'ilike'):
    create_lookup(hstore_lookups, lookup, HStoreLookupBase)


class IsNull(lookups.IsNull):
    def as_sql(self, qn, connection):
        output_field = self.lhs.output_field
        sql = output_field.db_field(qn, connection, self.lhs)

        if self.rhs:
            return "%s IS NULL" % sql, []
        else:
            return "%s IS NOT NULL" % sql, []


hstore_lookups['isnull'] = IsNull
create_lookup(hstore_lookups, 'data_contains', HStoreLookupBase, DataContains)
create_lookup(hstore_lookups, 'data_overlap', HStoreLookupBase, Overlap)
create_lookup(hstore_lookups, 'geo_dwithin', HStoreLookupBase, DWithinLookup)
