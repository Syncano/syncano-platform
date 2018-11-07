# coding=UTF8
from django.contrib.gis.db.backends.postgis.adapter import PostGISAdapter as _PostGISAdapter
from psycopg2.extras import Json as _Json


class Json(_Json):
    # Json adapter with eq and repr

    def __eq__(self, other):
        return (
            isinstance(other, Json) and
            self.adapted == other.adapted
        )

    def __repr__(self):
        return str(self.adapted)


class PostGISAdapter(_PostGISAdapter):
    def getquoted(self):
        # Casts to text so it is properly handled in hstore
        return '%s::text' % super().getquoted()
