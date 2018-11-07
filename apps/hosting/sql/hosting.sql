CREATE INDEX hosting_file_order_level ON hosting_hostingfile
USING BTREE (path, level DESC) WHERE _is_live=true;
