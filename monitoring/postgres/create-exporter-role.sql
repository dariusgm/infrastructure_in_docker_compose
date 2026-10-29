-- Dedicated login for postgres_exporter. Read-only: pg_monitor reads the statistics views and
-- grants no access to user data. Safe to run again: the password is updated, the grant repeats.
-- Run by the <name>-db-setup service with: psql -v exporter_password=... -f create-exporter-role.sql
\set ON_ERROR_STOP on

SELECT format('CREATE ROLE postgres_exporter LOGIN PASSWORD %L', :'exporter_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres_exporter')
\gexec

SELECT format('ALTER ROLE postgres_exporter LOGIN PASSWORD %L', :'exporter_password')
\gexec

GRANT pg_monitor TO postgres_exporter;
