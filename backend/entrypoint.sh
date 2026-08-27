#!/bin/sh
set -eu

if [ "${PROMETHEUS_MULTIPROC_DIR:-}" = "/tmp/tandem-prometheus" ]; then
    mkdir -p -m 700 "$PROMETHEUS_MULTIPROC_DIR"
    find "$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -maxdepth 1 -type f -delete
elif [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
    echo "PROMETHEUS_MULTIPROC_DIR must be /tmp/tandem-prometheus" >&2
    exit 1
fi

exec "$@"
