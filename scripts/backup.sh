#!/bin/sh
set -eu
umask 077
: "${BACKUP_DIR:?Set BACKUP_DIR to the mounted NAS destination}"
mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/photography-events-$(date -u +%Y%m%dT%H%M%SZ).dump"
trap 'rm -f "$file.partial"' EXIT
trap 'exit 1' HUP INT TERM
# Redirect in a POSIX shell so custom-format binary output is not transcoded.
docker compose exec -T photography-events-db pg_dump -U postgres -d photography_events -Fc --no-acl > "$file.partial"
mv "$file.partial" "$file"
printf '%s\n' "$file"
