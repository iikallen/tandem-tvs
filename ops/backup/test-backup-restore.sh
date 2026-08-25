#!/bin/sh
set -eu
umask 077

root_dir="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
work_dir="$(mktemp -d)"
restore_db="stage10_restore_$$"
restore_volume="tandem-stage10-restore-$$"
project="${COMPOSE_PROJECT_NAME:-tandem-tvs}"

cleanup() {
    docker compose -f "$root_dir/compose.yaml" exec -T postgres \
        dropdb --if-exists --force -U tandem "$restore_db" >/dev/null 2>&1 || true
    docker volume rm "$restore_volume" >/dev/null 2>&1 || true
    rm -rf -- "$work_dir"
}
trap cleanup EXIT HUP INT TERM

backup_dir="$work_dir/backup"
mkdir -m 700 "$backup_dir"

docker compose -f "$root_dir/compose.yaml" exec -T postgres \
    pg_dump --format=custom --no-owner --no-acl -U tandem tandem >"$backup_dir/database.dump"
docker compose -f "$root_dir/compose.yaml" exec -T frontend \
    tar -C /srv/media -cf - . >"$backup_dir/media.tar"
python3 "$root_dir/ops/backup/verify_manifest.py" create "$backup_dir"
python3 "$root_dir/ops/backup/verify_manifest.py" verify "$backup_dir"

docker compose -f "$root_dir/compose.yaml" exec -T postgres \
    createdb -U tandem "$restore_db"
docker compose -f "$root_dir/compose.yaml" exec -T postgres \
    pg_restore --exit-on-error --no-owner --no-acl -U tandem -d "$restore_db" \
    <"$backup_dir/database.dump"

docker volume create "$restore_volume" >/dev/null
docker run --rm -i -v "$restore_volume:/restore" tandem-tvs-postgres \
    tar -C /restore -xf - <"$backup_dir/media.tar"

docker run --rm \
    --network "${project}_default" \
    -v "$restore_volume:/app/media:ro" \
    -e DJANGO_SETTINGS_MODULE=config.settings.development \
    -e DATABASE_URL="postgresql://tandem:tandem-development-only@postgres:5432/$restore_db" \
    -e REDIS_URL=redis://redis:6379/0 \
    -e MEDIA_ROOT=/app/media \
    tandem-tvs-backend \
    uv run --no-sync python manage.py verify_restored_state

echo "Backup/restore drill: PASS"
