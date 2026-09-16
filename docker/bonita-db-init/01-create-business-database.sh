#!/bin/sh
set -eu

: "${BIZ_DB_NAME:?BIZ_DB_NAME es obligatoria}"
: "${BIZ_DB_USER:?BIZ_DB_USER es obligatoria}"
: "${BIZ_DB_PASS:?BIZ_DB_PASS es obligatoria}"

psql \
    --set=ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set=biz_db_name="$BIZ_DB_NAME" \
    --set=biz_db_user="$BIZ_DB_USER" \
    --set=biz_db_pass="$BIZ_DB_PASS" <<-'SQL'
SELECT format(
    'CREATE ROLE %I WITH LOGIN PASSWORD %L',
    :'biz_db_user',
    :'biz_db_pass'
)
WHERE NOT EXISTS (
    SELECT FROM pg_catalog.pg_roles WHERE rolname = :'biz_db_user'
) \gexec

SELECT format(
    'CREATE DATABASE %I OWNER %I',
    :'biz_db_name',
    :'biz_db_user'
)
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = :'biz_db_name'
) \gexec
SQL
