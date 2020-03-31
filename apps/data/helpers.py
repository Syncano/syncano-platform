# coding=UTF8
import os

from django.core.files.storage import default_storage
from django.db import connection, connections, models

from apps.core.helpers import generate_key, import_class
from apps.instances.helpers import get_current_instance, get_instance_db


def upload_file_to(instance, filename):
    _, ext = os.path.splitext(filename)
    return '{instance_prefix}/{klass_id}/{filename}{ext}'.format(
        instance_prefix=get_current_instance().get_storage_prefix(),
        klass_id=instance._klass_id,
        filename=generate_key(),
        ext=ext.lower()[:16]  # extensions longer than 16 would be kinda strange
    )


FIELD_CLASS_MAP = {
    'string': ('apps.data.fields.CharField', {'max_length': 128}),
    'text': ('apps.data.fields.TextField', {'max_length': 32000}),
    'integer': ('apps.data.fields.IncrementableIntegerField', {}),
    'float': ('apps.data.fields.IncrementableFloatField', {}),
    'boolean': ('apps.data.fields.NullBooleanField', {}),
    'datetime': ('apps.data.fields.DateTimeField', {}),
    'file': ('apps.data.fields.HStoreFileField', {
        'upload_to': upload_file_to,
        'storage': default_storage,
        'max_length': None,
    }),
    'reference': ('apps.data.fields.ReferenceField', {}),
    'object': ('apps.data.fields.ObjectField', {}),
    'array': ('apps.data.fields.ArrayField', {}),
    'geopoint': ('apps.data.fields.PointField', {'geography': True}),
    'relation': ('apps.data.fields.RelationField', {}),
}

CHECK_INDEX_SQL = """
SELECT i.indisvalid AND i.indisready
FROM   pg_class c
JOIN   pg_namespace n ON n.oid = c.relnamespace
JOIN   pg_index i ON i.indexrelid = c.oid
WHERE  c.relname = %s
AND    n.nspname = %s
"""

INDEX_DATA = {
    'filter': {
        'default': (
            {
                'name': 'data_klass_{klass_pk}_filter_{field_name}',
                'using': 'btree(({db_type}))',
            },
        ),
        'string': (
            {
                'name': 'data_klass_{klass_pk}_filter_{field_name}',
                'using': 'btree(({db_type}))',
            },
            {
                'name': 'data_klass_{klass_pk}_trgm_filter_{field_name}',
                'using': 'gin(({db_type}) gin_trgm_ops)',
            },
        ),
        'array': (
            {
                'name': 'data_klass_{klass_pk}_filter_{field_name}',
                'using': 'gin(({db_type}) jsonb_path_ops)',
            },
        ),
        'geopoint': (
            {
                'name': 'data_klass_{klass_pk}_filter_{field_name}',
                'using': 'gist(({db_type}))',
            },
        ),
        'relation': (
            {
                'name': 'data_klass_{klass_pk}_filter_{field_name}',
                'using': 'gin(({db_type}))',
            },
        ),
    },
    'order': {
        'default': (
            {
                'name': 'data_klass_{klass_pk}_order_{field_name}',
                'using': 'btree(({db_type}), id)',
            },
        ),
    }
}

CREATE_INDEX_SQL = """
CREATE {unique} INDEX {concurrently} "{index_name}" ON data_dataobject
USING {index_using}
WHERE "_klass_id"=%s
"""

DROP_INDEX_SQL = """
DROP INDEX {concurrently} IF EXISTS "{index_name}"
"""

SELECT_INDEX_SQL = """
SELECT c.relname
FROM   pg_class c
JOIN   pg_namespace n ON n.oid = c.relnamespace
JOIN   pg_index i ON i.indexrelid = c.oid
WHERE  n.nspname = '{schema_name}'
AND    c.relname LIKE 'data\\_klass\\_{klass_pk}\\_%'
"""

CONCURRENTLY_KEYWORD = 'CONCURRENTLY'
UNIQUE_KEYWORD = 'UNIQUE'


def convert_field_class_to_db_type(field_source, field_internal_type, db_type, db_table='data_dataobject',
                                   hstore_field_name='_data'):
    qn = connection.ops.quote_name

    if field_internal_type == 'DateTimeField':
        return 'to_timestamp(%s.%s->\'%s\')' % (
            qn(db_table), qn(hstore_field_name), field_source)

    if field_internal_type == 'RelationField':
        return 'to_intarray(%s.%s->\'%s\')' % (
            qn(db_table), qn(hstore_field_name), field_source)

    return '(%s.%s->\'%s\')::%s' % (
        qn(db_table), qn(hstore_field_name), field_source,
        db_type)


def convert_field_type_to_db_type(field_source, field_type, db_table='data_dataobject', hstore_field_name='_data'):
    field_cls, params = FIELD_CLASS_MAP[field_type]

    if isinstance(field_cls, str):
        try:
            getattr(models, field_cls)
        except AttributeError:
            field_cls = import_class(field_cls)

    field_obj = field_cls(**params)
    return convert_field_class_to_db_type(field_source=field_source,
                                          field_internal_type=field_obj.get_internal_type(),
                                          db_type=field_obj.db_type(connection),
                                          db_table=db_table,
                                          hstore_field_name=hstore_field_name)


def process_data_object_index(instance, klass_pk, index_type, index_data,
                              concurrently=True, create=True):
    field_column = None
    index_flags = None
    if create:
        field_name, field_column, field_type, index_flags = index_data
    else:
        field_name, field_type = index_data

    db = get_instance_db(instance)
    cursor = connections[db].cursor()
    index_flags = index_flags or {}

    unique = index_flags.get('unique', False)
    unique_keyword = ''
    if unique:
        unique_keyword = 'UNIQUE'

    concurrently_keyword = ''
    if concurrently:
        concurrently_keyword = CONCURRENTLY_KEYWORD

    index_data = INDEX_DATA[index_type]
    index_data = index_data.get(field_type) or index_data['default']

    for idx, index_info in enumerate(index_data):
        index_name = index_info['name'].format(klass_pk=klass_pk,
                                               field_name=field_name)

        if create:
            if field_column is None:
                # This should never happen
                raise RuntimeError(
                    'Called process_data_object_index with create=True yet field_column is None.')  # pragma: no cover

            cursor.execute(CHECK_INDEX_SQL, (index_name, instance.schema_name))
            row = cursor.fetchone()
            if row:
                # Selects true when index is valid and ready
                if row[0]:
                    return
                # Otherwise drop it
                cursor.execute(DROP_INDEX_SQL.format(index_name=index_name, concurrently=concurrently_keyword))

            index_using = index_info['using'].format(db_type=field_column)
            # Only first index should be unique (and created non-concurrently)
            sql = CREATE_INDEX_SQL.format(index_name=index_name,
                                          concurrently='' if idx == 0 and unique else concurrently_keyword,
                                          index_using=index_using,
                                          unique=unique_keyword if idx == 0 else '')
            cursor.execute(sql, (klass_pk,))
        else:
            cursor.execute(DROP_INDEX_SQL.format(index_name=index_name, concurrently=concurrently_keyword))
