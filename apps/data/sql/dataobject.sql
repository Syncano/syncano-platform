CREATE FUNCTION to_timestamp(TEXT)
  RETURNS TIMESTAMPTZ AS $$
SELECT $1 :: TIMESTAMP AT TIME ZONE 'utc';
$$ LANGUAGE SQL IMMUTABLE;

CREATE FUNCTION to_intarray(TEXT)
  RETURNS INTEGER[] AS $$
SELECT $1 :: INTEGER[];
$$ LANGUAGE SQL IMMUTABLE;

CREATE FUNCTION count_estimate(query TEXT, real_limit INT DEFAULT 1000)
  RETURNS INTEGER AS
  $func$
  DECLARE
    rec       RECORD;
    count_rec RECORD;
    ret       INTEGER;
  BEGIN
    EXECUTE 'SELECT COUNT(*) FROM (' || query || ' LIMIT ' || real_limit + 1 || ') c'
    INTO count_rec;
    IF count_rec.count <= real_limit
    THEN
      RETURN count_rec.count;
    END IF;
    FOR rec IN EXECUTE 'EXPLAIN ' || query LOOP
      ret := SUBSTRING(rec."QUERY PLAN" FROM ' rows=([[:digit:]]+)');
      EXIT WHEN ret IS NOT NULL;
    END LOOP;

    RETURN GREATEST(ret, real_limit);
  END
  $func$ LANGUAGE plpgsql;

CREATE INDEX data_klass_order_created_at ON data_dataobject
USING BTREE (created_at, id);

CREATE INDEX data_klass_order_updated_at ON data_dataobject
USING BTREE (updated_at, id);

CREATE INDEX data_klass_acl_users ON data_dataobject
USING GIN (_users);

CREATE INDEX data_klass_acl_groups ON data_dataobject
USING GIN (_groups);

CREATE INDEX data_klass_acl_public ON data_dataobject
USING BTREE (_public) WHERE _public = true;
