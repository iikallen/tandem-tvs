#!/bin/sh
set -eu
umask 077

: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"
: "${DATABASE_URL:?DATABASE_URL of the protected production database is required}"
: "${BACKUP_DIR:?BACKUP_DIR is required}"
: "${RESTORE_MEDIA_ROOT:?RESTORE_MEDIA_ROOT is required}"
: "${RESTORE_CONFIRMATION:?Set RESTORE_CONFIRMATION=isolated-database}"

if [ "$RESTORE_CONFIRMATION" != "isolated-database" ]; then
    echo "Restore drill confirmation rejected" >&2
    exit 1
fi

PSQL="${PSQL:-psql}"
PG_RESTORE="${PG_RESTORE:-pg_restore}"
UV="${UV:-uv}"
PYTHON="${PYTHON:-python3}"

database_identity() {
    "$PSQL" -XAt --set=ON_ERROR_STOP=1 --dbname="$1" --command="SELECT concat_ws('|', inet_server_addr()::text, inet_server_port()::text, current_database(), (SELECT oid::text FROM pg_database WHERE datname = current_database()))"
}

if [ "$(database_identity "$DATABASE_URL")" = "$(database_identity "$RESTORE_DATABASE_URL")" ]; then
    echo "Refusing to restore into the canonical production database identity" >&2
    exit 1
fi

target_objects="$("$PSQL" -XAt --set=ON_ERROR_STOP=1 --dbname="$RESTORE_DATABASE_URL" --command="SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%'")"
if [ "$target_objects" != "0" ]; then
    echo "RESTORE_DATABASE_URL must identify a fresh empty database" >&2
    exit 1
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
backup_dir="$(CDPATH= cd -- "$BACKUP_DIR" && pwd -P)"
if command -v cygpath >/dev/null 2>&1; then
    script_dir="$(cygpath -m "$script_dir")"
    backup_dir="$(cygpath -m "$backup_dir")"
fi
"$PYTHON" "$script_dir/verify_manifest.py" verify "$backup_dir"

if [ -d "$RESTORE_MEDIA_ROOT" ] && [ "$(find "$RESTORE_MEDIA_ROOT" -mindepth 1 -print -quit)" ]; then
    echo "RESTORE_MEDIA_ROOT must be empty" >&2
    exit 1
fi
mkdir -p -m 700 "$RESTORE_MEDIA_ROOT"

echo "Restoring isolated PostgreSQL database"
"$PG_RESTORE" --exit-on-error --no-owner --no-acl \
    --dbname="$RESTORE_DATABASE_URL" <"$backup_dir/database.dump"

echo "Restoring isolated protected media"
tar -C "$RESTORE_MEDIA_ROOT" -xf - <"$backup_dir/media.tar"
if [ -n "${RESTORE_MEDIA_OWNER:-}" ]; then
    restore_uid="${RESTORE_MEDIA_OWNER%%:*}"
    restore_gid="${RESTORE_MEDIA_OWNER#*:}"
    case "$restore_uid" in ''|*[!0-9]*) restore_uid="" ;; esac
    case "$restore_gid" in ''|*[!0-9]*) restore_gid="" ;; esac
    if [ -z "$restore_uid" ] || [ -z "$restore_gid" ] || [ "$restore_uid:$restore_gid" != "$RESTORE_MEDIA_OWNER" ]; then
        echo "RESTORE_MEDIA_OWNER must be a numeric uid:gid" >&2
        exit 1
    fi
    chown -R "$RESTORE_MEDIA_OWNER" "$RESTORE_MEDIA_ROOT"
fi

DATABASE_URL="$RESTORE_DATABASE_URL" MEDIA_ROOT="$RESTORE_MEDIA_ROOT" \
    "$UV" run --no-sync python manage.py verify_restored_state
echo "Restore drill: PASS"
