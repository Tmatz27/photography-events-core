#!/bin/sh
set -eu
# initdb only: application owns its dedicated DB but has no superuser powers.
# PostGIS is enabled by the image's preceding 10_postgis initialization.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE photography_events LOGIN PASSWORD :'app_password';
ALTER DATABASE photography_events OWNER TO photography_events;
GRANT USAGE, CREATE ON SCHEMA public TO photography_events;
SQL
