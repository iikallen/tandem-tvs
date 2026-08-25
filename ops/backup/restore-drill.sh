#!/bin/sh
set -eu
umask 077

: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"
: "${BACKUP_DIR:?BACKUP_DIR is required}"
: "${RESTORE_MEDIA_ROOT:?RESTORE_MEDIA_ROOT is required}"
: "${RESTORE_CONFIRMATION:?Set RESTORE_CONFIRMATION=isolated-database}"

if [ "$RESTORE_CONFIRMATION" != "isolated-database" ]; then
    echo "Restore drill confirmation rejected" >&2
    exit 1
fi
if [ "${DATABASE_URL:-}" = "$RESTORE_DATABASE_URL" ]; then
    echo "Refusing to restore into DATABASE_URL" >&2
    exit 1
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
backup_dir="$(CDPATH= cd -- "$BACKUP_DIR" && pwd -P)"
python3 "$script_dir/verify_manifest.py" verify "$backup_dir"

if [ -d "$RESTORE_MEDIA_ROOT" ] && [ "$(find "$RESTORE_MEDIA_ROOT" -mindepth 1 -print -quit)" ]; then
    echo "RESTORE_MEDIA_ROOT must be empty" >&2
    exit 1
fi
mkdir -p -m 700 "$RESTORE_MEDIA_ROOT"

echo "Restoring isolated PostgreSQL database"
pg_restore --clean --if-exists --exit-on-error --no-owner --no-acl \
    --dbname="$RESTORE_DATABASE_URL" "$backup_dir/database.dump"

echo "Restoring isolated protected media"
tar -C "$RESTORE_MEDIA_ROOT" -xf "$backup_dir/media.tar"

DATABASE_URL="$RESTORE_DATABASE_URL" MEDIA_ROOT="$RESTORE_MEDIA_ROOT" \
    uv run --no-sync python manage.py verify_restored_state
echo "Restore drill: PASS"
