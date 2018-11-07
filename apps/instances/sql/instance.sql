CREATE INDEX instance_name_like ON instances_instance
USING BTREE (name varchar_pattern_ops);
