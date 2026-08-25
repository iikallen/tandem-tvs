#!/bin/sh
set -eu
umask 077

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_ROOT:?BACKUP_ROOT is required}"
: "${MEDIA_ROOT:?MEDIA_ROOT is required}"
: "${POSTGRES_DATA_ROOT:?POSTGRES_DATA_ROOT mount marker is required}"

PSQL="${PSQL:-psql}"
PG_DUMP="${PG_DUMP:-pg_dump}"
BACKUP_WRITE_LOCK_ID=82425010

mkdir -p -m 700 "$BACKUP_ROOT"
backup_root="$(CDPATH= cd -- "$BACKUP_ROOT" && pwd -P)"
media_root="$(CDPATH= cd -- "$MEDIA_ROOT" && pwd -P)"
postgres_data_root="$(CDPATH= cd -- "$POSTGRES_DATA_ROOT" && pwd -P)"

for source_root in "$media_root" "$postgres_data_root"; do
    case "$backup_root/" in "$source_root/"*)
        echo "BACKUP_ROOT must not be inside a source data mount" >&2
        exit 1
    esac
    case "$source_root/" in "$backup_root/"*)
        echo "BACKUP_ROOT must be a separate corporate backup mount" >&2
        exit 1
    esac
    if [ "$(stat -c %d "$backup_root")" = "$(stat -c %d "$source_root")" ]; then
        echo "BACKUP_ROOT must be outside the PostgreSQL and media failure domains" >&2
        exit 1
    fi
done

operation_lock="$backup_root/.backup.lock"
if ! mkdir -m 700 "$operation_lock"; then
    echo "Another backup is active, or a stale backup lock needs operator review" >&2
    exit 1
fi

temporary=""
database_lock_pid=""
cleanup() {
    if [ -n "$database_lock_pid" ]; then
        kill "$database_lock_pid" >/dev/null 2>&1 || true
        wait "$database_lock_pid" >/dev/null 2>&1 || true
    fi
    if [ -n "$temporary" ]; then
        rm -rf -- "$temporary"
    fi
    rmdir "$operation_lock" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$backup_root/$timestamp"
temporary="$backup_root/.${timestamp}.tmp.$$"
test ! -e "$target"
mkdir -m 700 "$temporary"

database_identity="$("$PSQL" -XAt --set=ON_ERROR_STOP=1 --dbname="$DATABASE_URL" --command="SELECT concat_ws('|', inet_server_addr()::text, inet_server_port()::text, current_database(), (SELECT oid::text FROM pg_database WHERE datname = current_database()))")"
printf '%s\n' \
    "database_identity=$database_identity" \
    "postgres_data_root=$postgres_data_root" \
    "postgres_data_device=$(stat -c %d "$postgres_data_root")" \
    "media_root=$media_root" \
    "media_device=$(stat -c %d "$media_root")" \
    "backup_root=$backup_root" \
    "backup_device=$(stat -c %d "$backup_root")" \
    >"$temporary/source-evidence.txt"

lock_application="tandem-backup-$$"
PGAPPNAME="$lock_application" "$PSQL" -XqAt --set=ON_ERROR_STOP=1 \
    --dbname="$DATABASE_URL" \
    --command="SELECT pg_advisory_lock($BACKUP_WRITE_LOCK_ID); SELECT pg_sleep(86400);" \
    >/dev/null 2>&1 &
database_lock_pid=$!
lock_attempt=0
while :; do
    lock_count="$("$PSQL" -XAt --set=ON_ERROR_STOP=1 --dbname="$DATABASE_URL" --command="SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid WHERE a.application_name = '$lock_application' AND l.locktype = 'advisory' AND l.mode = 'ExclusiveLock' AND l.granted")"
    [ "$lock_count" = "1" ] && break
    if ! kill -0 "$database_lock_pid" 2>/dev/null || [ "$lock_attempt" -ge 60 ]; then
        echo "Could not acquire the application backup write lock" >&2
        exit 1
    fi
    lock_attempt=$((lock_attempt + 1))
    sleep 1
done

echo "Creating PostgreSQL backup"
"$PG_DUMP" --format=custom --no-owner --no-acl "$DATABASE_URL" >"$temporary/database.dump"

echo "Creating protected-media backup"
tar -C "$media_root" -cf "$temporary/media.tar" .
(cd "$temporary" && sha256sum database.dump media.tar source-evidence.txt >SHA256SUMS)
printf '%s\n' "$timestamp" >"$temporary/created-at.txt"
mv "$temporary" "$target"
kill "$database_lock_pid" >/dev/null 2>&1 || true
wait "$database_lock_pid" >/dev/null 2>&1 || true
database_lock_pid=""
rmdir "$operation_lock"
trap - EXIT HUP INT TERM
echo "Backup complete: $target"
