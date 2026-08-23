#!/bin/sh
set -eu

uv run --no-sync python manage.py migrate --noinput
exec "$@"
