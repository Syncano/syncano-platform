CREATE INDEX admins_admin_trgm_email ON admins_admin
USING GIN (email gin_trgm_ops);

CREATE INDEX admins_admin_noticed_at ON admins_admin
USING BTREE (noticed_at)
WHERE noticed_at IS NOT NULL;
