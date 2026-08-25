#!/bin/sh
set -eu
umask 077

root_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
work_dir="$(mktemp -d)"
restore_db="stage10_restore_$$"
nonempty_db="stage10_nonempty_$$"
compose_file="$root_dir/compose.yaml"

cleanup() {
    docker compose -f "$compose_file" exec -T postgres \
        dropdb --if-exists --force -U tandem "$restore_db" >/dev/null 2>&1 || true
    docker compose -f "$compose_file" exec -T postgres \
        dropdb --if-exists --force -U tandem "$nonempty_db" >/dev/null 2>&1 || true
    rm -rf -- "$work_dir"
}
trap cleanup EXIT HUP INT TERM

postgres_id="$(docker compose -f "$compose_file" ps -q postgres)"
backend_id="$(docker compose -f "$compose_file" ps -q backend)"
postgres_image="$(docker inspect --format '{{.Config.Image}}' "$postgres_id")"
backend_image="$(docker inspect --format '{{.Config.Image}}' "$backend_id")"
network="$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{end}}' "$postgres_id")"
postgres_volume="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql"}}{{.Name}}{{end}}{{end}}' "$postgres_id")"
media_volume="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/media"}}{{.Name}}{{end}}{{end}}' "$backend_id")"
test -n "$network"
test -n "$postgres_volume"
test -n "$media_volume"

production_url="postgresql://tandem:tandem-development-only@postgres:5432/tandem"
backup_archive="$work_dir/backup.tar"
docker run --rm --network "$network" \
    --tmpfs /backup:rw,noexec,nosuid,nodev,mode=0700 \
    -v "$postgres_volume:/postgres-data:ro" \
    -v "$media_volume:/media:ro" \
    -v "$root_dir/ops/backup:/scripts:ro" \
    -e DATABASE_URL="$production_url" \
    -e BACKUP_ROOT=/backup \
    -e MEDIA_ROOT=/media \
    -e POSTGRES_DATA_ROOT=/postgres-data \
    "$postgres_image" sh -c 'mkdir /backup/.backup.lock; if /scripts/backup.sh; then exit 1; fi; rmdir /backup/.backup.lock; /scripts/backup.sh >&2; tar -C /backup -cf - .' \
    >"$backup_archive"

backup_root="$work_dir/backup"
mkdir -m 700 "$backup_root"
tar -C "$backup_root" -xf "$backup_archive"
backup_dir="$(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -print -quit)"
test -n "$backup_dir"

wrapper_dir="$work_dir/bin"
mkdir -m 700 "$wrapper_dir"
cat >"$wrapper_dir/psql" <<'EOF'
#!/bin/sh
exec docker compose -f "$COMPOSE_FILE_PATH" exec -T postgres psql "$@"
EOF
cat >"$wrapper_dir/pg_restore" <<'EOF'
#!/bin/sh
exec docker compose -f "$COMPOSE_FILE_PATH" exec -T postgres pg_restore "$@"
EOF
cat >"$wrapper_dir/uv" <<'EOF'
#!/bin/sh
exec docker run --rm --network "$RESTORE_NETWORK" \
    -v "$MEDIA_ROOT:/app/media" \
    -e DJANGO_SETTINGS_MODULE=config.settings.development \
    -e DATABASE_URL="$DATABASE_URL" \
    -e REDIS_URL=redis://redis:6379/0 \
    -e MEDIA_ROOT=/app/media \
    "$BACKEND_IMAGE" uv "$@"
EOF
chmod 700 "$wrapper_dir/psql" "$wrapper_dir/pg_restore" "$wrapper_dir/uv"
export COMPOSE_FILE_PATH="$compose_file"
export RESTORE_NETWORK="$network"
export BACKEND_IMAGE="$backend_image"

docker compose -f "$compose_file" exec -T postgres \
    createdb --template=template0 -U tandem "$restore_db"
docker compose -f "$compose_file" exec -T postgres \
    createdb --template=template0 -U tandem "$nonempty_db"
docker compose -f "$compose_file" exec -T postgres \
    psql -X -U tandem -d "$nonempty_db" -c 'CREATE TABLE must_not_be_deleted (id integer)' \
    >/dev/null

restore_media="$work_dir/restore-media"
if (
    cd "$root_dir/backend"
    DATABASE_URL="$production_url" \
        RESTORE_DATABASE_URL="$production_url" \
        BACKUP_DIR="$backup_dir" \
        RESTORE_MEDIA_ROOT="$restore_media" \
        RESTORE_CONFIRMATION=isolated-database \
        PSQL="$wrapper_dir/psql" PG_RESTORE="$wrapper_dir/pg_restore" UV="$wrapper_dir/uv" \
        ../ops/backup/restore-drill.sh
); then
    echo "Restore drill accepted the production database" >&2
    exit 1
fi

if (
    cd "$root_dir/backend"
    DATABASE_URL="$production_url" \
        RESTORE_DATABASE_URL="postgresql://tandem:tandem-development-only@postgres:5432/$nonempty_db" \
        BACKUP_DIR="$backup_dir" \
        RESTORE_MEDIA_ROOT="$restore_media" \
        RESTORE_CONFIRMATION=isolated-database \
        PSQL="$wrapper_dir/psql" PG_RESTORE="$wrapper_dir/pg_restore" UV="$wrapper_dir/uv" \
        ../ops/backup/restore-drill.sh
); then
    echo "Restore drill accepted a non-empty database" >&2
    exit 1
fi

(
    cd "$root_dir/backend"
    DATABASE_URL="$production_url" \
        RESTORE_DATABASE_URL="postgresql://tandem:tandem-development-only@postgres:5432/$restore_db" \
        BACKUP_DIR="$backup_dir" \
        RESTORE_MEDIA_ROOT="$restore_media" \
        RESTORE_CONFIRMATION=isolated-database \
        PSQL="$wrapper_dir/psql" PG_RESTORE="$wrapper_dir/pg_restore" UV="$wrapper_dir/uv" \
        ../ops/backup/restore-drill.sh
)

docker compose -f "$compose_file" exec -T postgres \
    psql -XAt -U tandem -d "$nonempty_db" -c \
    "SELECT count(*) FROM pg_class WHERE relname = 'must_not_be_deleted'" \
    | grep -qx 1

echo "Backup/restore drill: PASS"
