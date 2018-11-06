# coding=UTF8
from django.db.backends.base.introspection import TableInfo
from django.db.backends.postgresql.introspection import DatabaseIntrospection as DatabaseIntrospection_
from django.db.backends.postgresql.introspection import FieldInfo
from django.db.models import Index
from django.utils.encoding import force_text


class DatabaseIntrospection(DatabaseIntrospection_):
    def get_table_list(self, cursor):
        "Returns a list of table names in the current database."
        schema_name = self.connection.schema_name
        cursor.execute("""
            SELECT c.relname, c.relkind
            FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'v', '')
                AND n.nspname = %s""", [schema_name])
        return [TableInfo(row[0], {'r': 't', 'v': 'v'}.get(row[1]))
                for row in cursor.fetchall()
                if row[0] not in self.ignored_tables]

    def get_table_description(self, cursor, table_name):
        "Returns a description of the table, with the DB-API cursor.description interface."
        # As cursor.description does not return reliably the nullable property,
        # we have to query the information_schema (#7783)
        schema_name = self.connection.schema_name
        cursor.execute("""
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_name = %s
                AND table_schema = %s""", [table_name, schema_name])
        null_map = dict(cursor.fetchall())
        cursor.execute("SELECT * FROM %s LIMIT 1" % self.connection.ops.quote_name(table_name))
        return [FieldInfo(*((force_text(line[0]),) + line[1:6] + (null_map[force_text(line[0])] == 'YES',)))
                for line in cursor.description]

    def get_relations(self, cursor, table_name):
        """
        Returns a dictionary of {field_index: (field_index_other_table, other_table)}
        representing all relationships to the given table. Indexes are 0-based.
        """
        schema_name = self.connection.schema_name
        cursor.execute("""
            SELECT con.conkey, con.confkey, c2.relname
            FROM pg_constraint con, pg_class c1, pg_class c2, pg_catalog.pg_namespace n
            WHERE c1.oid = con.conrelid
                AND n.oid = c1.relnamespace
                AND n.nspname = %s
                AND c2.oid = con.confrelid
                AND c1.relname = %s
                AND con.contype = 'f'""", [schema_name, table_name])
        relations = {}
        for row in cursor.fetchall():
            # row[0] and row[1] are single-item lists, so grab the single item.
            relations[row[0][0] - 1] = (row[1][0] - 1, row[2])
        return relations

    def get_key_columns(self, cursor, table_name):
        schema_name = self.connection.schema_name
        key_columns = []
        cursor.execute("""
            SELECT a.attname AS column_name, r2.relname AS referenced_table, a2.attname AS referenced_column
            FROM pg_namespace nr, pg_class r, pg_attribute a, pg_namespace nc, pg_constraint c,
                pg_attribute a2, pg_class r2
            WHERE nc.nspname = %s
                AND r.relname = %s
                AND nr.oid = r.relnamespace
                AND r.oid = a.attrelid
                AND nc.oid = c.connamespace
                AND r.oid = c.conrelid
                AND a.attnum = ANY (c.conkey)
                AND NOT a.attisdropped
                AND c.contype = 'f'
                AND r.relkind = 'r'
                AND a2.attnum = ANY(c.confkey)
                AND a2.attrelid = c.confrelid
                AND r2.oid = a2.attrelid""", [schema_name, table_name])
        key_columns.extend(cursor.fetchall())
        return key_columns

    def get_indexes(self, cursor, table_name):
        # This query retrieves each index on the given table, including the
        # first associated field name
        schema_name = self.connection.schema_name
        cursor.execute("""
            SELECT attr.attname, idx.indkey, idx.indisunique, idx.indisprimary
            FROM pg_catalog.pg_class c, pg_catalog.pg_class c2,
                pg_catalog.pg_index idx, pg_catalog.pg_attribute attr,
                pg_catalog.pg_namespace n
            WHERE c.oid = idx.indrelid
                AND n.oid = c.relnamespace
                AND n.nspname = %s
                AND idx.indexrelid = c2.oid
                AND attr.attrelid = c.oid
                AND attr.attnum = idx.indkey[0]
                AND c.relname = %s""", [schema_name, table_name])
        indexes = {}
        for row in cursor.fetchall():
            # row[1] (idx.indkey) is stored in the DB as an array. It comes out as
            # a string of space-separated integers. This designates the field
            # indexes (1-based) of the fields that have indexes on the table.
            # Here, we skip any indexes across multiple fields.
            if ' ' in row[1]:
                continue
            if row[0] not in indexes:
                indexes[row[0]] = {'primary_key': False, 'unique': False}
            # It's possible to have the unique and PK constraints in separate indexes.
            if row[3]:
                indexes[row[0]]['primary_key'] = True
            if row[2]:
                indexes[row[0]]['unique'] = True
        return indexes

    def get_constraints(self, cursor, table_name):
        """
        Retrieves any constraints or keys (unique, pk, fk, check, index) across one or more columns.
        """
        constraints = {}
        schema_name = self.connection.schema_name

        # Loop over the key table, collecting things as constraints
        # This will get PKs, FKs, and uniques, but not CHECK
        cursor.execute("""
            SELECT c.conname,
                array(
                    SELECT attname
                    FROM (
                        SELECT unnest(c.conkey) AS colid,
                               generate_series(1, array_length(c.conkey, 1)) AS arridx
                    ) AS cols
                    JOIN pg_attribute AS ca ON cols.colid = ca.attnum
                    WHERE ca.attrelid = c.conrelid
                    ORDER BY cols.arridx
                ),
                c.contype,
                (SELECT fkc.relname || '.' || fka.attname
                FROM pg_attribute AS fka
                JOIN pg_class AS fkc ON fka.attrelid = fkc.oid
                WHERE fka.attrelid = c.confrelid AND fka.attnum = c.confkey[1]),
                cl.reloptions
            FROM pg_constraint AS c
            JOIN pg_class AS cl ON c.conrelid = cl.oid
            JOIN pg_namespace AS ns ON cl.relnamespace = ns.oid
            WHERE ns.nspname = %s AND cl.relname = %s
        """, [schema_name, table_name])
        for constraint, columns, kind, used_cols, options in cursor.fetchall():
            constraints[constraint] = {
                "columns": columns,
                "primary_key": kind == "p",
                "unique": kind in ["p", "u"],
                "foreign_key": tuple(used_cols.split(".", 1)) if kind == "f" else None,
                "check": kind == "c",
                "index": False,
                "definition": None,
                "options": options,
            }

        # Now get indexes
        # The row_number() function for ordering the index fields can be
        # replaced by WITH ORDINALITY in the unnest() functions when support
        # for PostgreSQL 9.3 is dropped.
        cursor.execute("""
            SELECT
                indexname, array_agg(attname ORDER BY rnum), indisunique, indisprimary,
                array_agg(ordering ORDER BY rnum), amname, exprdef, s2.attoptions
            FROM (
                SELECT
                    row_number() OVER () as rnum, c2.relname as indexname,
                    idx.*, attr.attname, am.amname,
                    CASE
                        WHEN idx.indexprs IS NOT NULL THEN
                            pg_get_indexdef(idx.indexrelid)
                    END AS exprdef,
                    CASE am.amname
                        WHEN 'btree' THEN
                            CASE (option & 1)
                                WHEN 1 THEN 'DESC' ELSE 'ASC'
                            END
                    END as ordering,
                    c2.reloptions as attoptions
                FROM (
                    SELECT
                        *, unnest(i.indkey) as key, unnest(i.indoption) as option
                    FROM pg_index i
                ) idx
                LEFT JOIN pg_class c ON idx.indrelid = c.oid
                LEFT JOIN pg_class c2 ON idx.indexrelid = c2.oid
                LEFT JOIN pg_am am ON c2.relam = am.oid
                LEFT JOIN pg_attribute attr ON attr.attrelid = c.oid AND attr.attnum = idx.key
                JOIN pg_namespace AS ns ON c.relnamespace = ns.oid
                WHERE ns.nspname = %s AND c.relname = %s
            ) s2
            GROUP BY indexname, indisunique, indisprimary, amname, exprdef, attoptions;
        """, [schema_name, table_name])
        for index, columns, unique, primary, orders, type_, definition, options in cursor.fetchall():
            if index not in constraints:
                constraints[index] = {
                    "columns": columns if columns != [None] else [],
                    "orders": orders if orders != [None] else [],
                    "primary_key": primary,
                    "unique": unique,
                    "foreign_key": None,
                    "check": False,
                    "index": True,
                    "type": Index.suffix if type_ == 'btree' else type_,
                    "definition": definition,
                    "options": options,
                }
        return constraints
