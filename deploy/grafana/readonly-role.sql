-- Read-only role for the Grafana dashboard (DESIGN_MONITORING.md).
--
-- Grafana must never be able to modify application data, so it gets its own role with
-- SELECT on exactly the observability tables and nothing else. Run once per database:
--   docker exec -i <postgres> psql -U <app_user> -d <db> < readonly-role.sql
--
-- The password is supplied by the caller via psql -v, so it never lives in the repo.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        CREATE ROLE grafana_ro LOGIN;
    END IF;
END
$$;

ALTER ROLE grafana_ro WITH PASSWORD :'grafana_password';

GRANT CONNECT ON DATABASE :"db_name" TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON error_logs TO grafana_ro;
-- error_logs is monthly RANGE partitioned; the grant on the parent does not cascade to
-- partitions created later, so future partitions are covered by a default privilege.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
DO $$
DECLARE part text;
BEGIN
    FOR part IN
        SELECT c.relname FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        JOIN pg_class p ON p.oid = i.inhparent
        WHERE p.relname = 'error_logs'
    LOOP
        EXECUTE format('GRANT SELECT ON public.%I TO grafana_ro', part);
    END LOOP;
END
$$;
