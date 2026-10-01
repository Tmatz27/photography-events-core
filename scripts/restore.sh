#!/bin/sh
set -eu
: "${1:?Usage: restore.sh backup.dump new_database_name}"
: "${2:?Specify a NEW empty database name; never restore over production}"
case "$2" in photography_events|postgres|template0|template1|*[!a-z0-9_]*|'') echo 'Unsafe target database name' >&2; exit 2;; esac
# createdb fails if the destination exists. There is deliberately no --clean,
# DROP DATABASE or overwrite option in this operator-facing script.
docker compose exec -T photography-events-db createdb -U postgres -O photography_events "$2"
docker compose exec -T photography-events-db psql -U postgres -d "$2" -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS postgis'
# Restore as the DB administrator so all image-supplied PostGIS extensions can
# be recreated. Preserve archive ownership: application tables remain owned by
# the existing non-superuser photography_events role, extension objects by postgres.
docker compose exec -T photography-events-db pg_restore -U postgres -d "$2" --no-acl --exit-on-error < "$1"
docker compose run --rm --no-deps -e "POSTGRES_DB=$2" photography-events-core python -m alembic upgrade head
printf 'Restored and migrated %s. Verify readiness and data before any cutover.\n' "$2"
