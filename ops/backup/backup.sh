#!/bin/sh
set -eu
umask 077

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_ROOT:?BACKUP_ROOT is required}"
: "${MEDIA_ROOT:?MEDIA_ROOT is required}"

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
mkdir -p -m 700 "$BACKUP_ROOT"
backup_root="$(CDPATH= cd -- "$BACKUP_ROOT" && pwd -P)"
media_root="$(CDPATH= cd -- "$MEDIA_ROOT" && pwd -P)"

case "$backup_root/" in "$media_root/"*)
    echo "BACKUP_ROOT must not be inside MEDIA_ROOT" >&2
    exit 1
esac
case "$media_root/" in "$backup_root/"*)
    echo "BACKUP_ROOT must be a separate corporate backup mount" >&2
    exit 1
esac
if [ "$(stat -c %d "$backup_root")" = "$(stat -c %d "$media_root")" ]; then
    echo "BACKUP_ROOT and MEDIA_ROOT must be on different mounted filesystems" >&2
    exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$backup_root/$timestamp"
temporary="$backup_root/.${timestamp}.tmp.$$"
test ! -e "$target"
mkdir -m 700 "$temporary"
trap 'rm -rf -- "$temporary"' EXIT HUP INT TERM

echo "Creating PostgreSQL backup"
pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" >"$temporary/database.dump"

echo "Creating protected-media backup"
tar -C "$media_root" -cf "$temporary/media.tar" .
python3 "$script_dir/verify_manifest.py" create "$temporary"
printf '%s\n' "$timestamp" >"$temporary/created-at.txt"
mv "$temporary" "$target"
trap - EXIT HUP INT TERM
echo "Backup complete: $target"
