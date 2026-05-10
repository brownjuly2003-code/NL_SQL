-- Postgres initialisation for NL_SQL demo.
-- Sets up a read-only role + per-database safety defaults.
-- Run automatically by docker-entrypoint-initdb.d on first container boot.

-- 1. Read-only role used by the NL→SQL pipeline. Cannot create, write, or alter.
CREATE ROLE nl_sql_ro WITH LOGIN PASSWORD 'nl_sql_ro_pwd' NOINHERIT;
REVOKE ALL ON DATABASE nl_sql_demo FROM nl_sql_ro;
GRANT CONNECT ON DATABASE nl_sql_demo TO nl_sql_ro;
GRANT USAGE ON SCHEMA public TO nl_sql_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO nl_sql_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO nl_sql_ro;

-- 2. Hard lock the role to read-only transactions and bound resources.
ALTER ROLE nl_sql_ro SET default_transaction_read_only = on;
ALTER ROLE nl_sql_ro SET statement_timeout = '30s';
ALTER ROLE nl_sql_ro SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE nl_sql_ro SET temp_file_limit = '256MB';
ALTER ROLE nl_sql_ro SET search_path = public, pg_catalog;
