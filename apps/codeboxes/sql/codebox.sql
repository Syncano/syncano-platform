CREATE INDEX codebox_label_like ON codeboxes_codebox
USING BTREE (label varchar_pattern_ops);
