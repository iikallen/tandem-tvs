#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVICES = (
    "redis",
    "celery-worker",
    "celery-beat",
    "backend",
    "frontend",
    "cloudflared",
    "postgres",
)


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        check=True,
        encoding="utf-8",
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def wait_running(compose: list[str], service: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        output = run([*compose, "ps", "--format", "json", service], capture=True)
        if output:
            try:
                parsed = json.loads(output)
                rows = parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                rows = [json.loads(line) for line in output.splitlines()]
            if rows and all(
                row.get("State") == "running" and row.get("Health", "") in {"", "healthy"}
                for row in rows
            ):
                return
        time.sleep(2)
    raise RuntimeError(f"{service} did not return to running state in {timeout}s")


def wait_ready(url: str, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.HTTPError):
            pass
        time.sleep(2)
    raise RuntimeError(f"{url} did not become ready in {timeout}s")


def wait_unavailable(url: str, timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status != 200:
                    return
        except (OSError, urllib.error.HTTPError):
            return
        time.sleep(2)
    raise RuntimeError(f"{url} remained available during the injected fault")


def snapshot(compose: list[str]) -> dict[str, object]:
    output = run(
        [
            *compose,
            "exec",
            "-T",
            "backend",
            "uv",
            "run",
            "--no-sync",
            "python",
            "manage.py",
            "fault_snapshot",
        ],
        capture=True,
    )
    return json.loads(output.splitlines()[-1])


def backend_manage(compose: list[str], *arguments: str) -> str:
    return run(
        [
            *compose,
            "exec",
            "-T",
            "backend",
            "uv",
            "run",
            "--no-sync",
            "python",
            "manage.py",
            *arguments,
        ],
        capture=True,
    )


def create_probe(compose: list[str], label: str) -> str:
    output = backend_manage(compose, "fault_probe", "create", label)
    payload = json.loads(output.splitlines()[-1])
    if not payload.get("created"):
        raise RuntimeError("Fault probe reused an existing message")
    return str(payload["message_id"])


def verify_probe(compose: list[str], message_id: str, timeout: int) -> None:
    backend_manage(compose, "fault_probe", "verify", message_id, "--timeout", str(timeout))


def current_database(compose: list[str]) -> str:
    output = backend_manage(
        compose,
        "shell",
        "-c",
        "from django.db import connection; print(connection.settings_dict['NAME'])",
    )
    return output.splitlines()[-1]


def wait_heartbeat_stale(compose: list[str], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            backend_manage(compose, "fault_probe", "heartbeat-stale")
            return
        except subprocess.CalledProcessError:
            time.sleep(3)
    raise RuntimeError("Celery Beat heartbeat did not become observably stale")


def verify(compose: list[str], baseline: dict[str, object]) -> None:
    if snapshot(compose) != baseline:
        raise RuntimeError("Committed source-data digest changed during fault injection")
    run(
        [
            *compose,
            "exec",
            "-T",
            "backend",
            "uv",
            "run",
            "--no-sync",
            "python",
            "manage.py",
            "verify_media_integrity",
        ]
    )
    run(
        [
            *compose,
            "exec",
            "-T",
            "backend",
            "uv",
            "run",
            "--no-sync",
            "python",
            "scripts/verify_stage10.py",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Stage 10 isolated Compose fault matrix.")
    parser.add_argument("--compose-file", action="append", default=[])
    parser.add_argument("--project-name", required=True)
    parser.add_argument(
        "--ready-url",
        default=os.environ.get("TANDEM_READY_URL", "http://localhost:8080/api/v1/health/ready"),
    )
    parser.add_argument(
        "--external-ready-url",
        default=os.environ.get("TANDEM_EXTERNAL_READY_URL", ""),
        help="Cloudflare hostname readiness URL, required to test the tunnel fault.",
    )
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if os.environ.get("FAULT_TEST_CONFIRMATION") != "isolated-environment":
        parser.error("set FAULT_TEST_CONFIRMATION=isolated-environment")
    if os.environ.get("TANDEM_ENVIRONMENT_PURPOSE") != "stage10-load":
        parser.error("set TANDEM_ENVIRONMENT_PURPOSE=stage10-load")
    if not re.fullmatch(r"stage10-fault-[a-z0-9-]+", args.project_name):
        parser.error("--project-name must match stage10-fault-<isolated-id>")
    if not args.external_ready_url.startswith("https://"):
        parser.error("set TANDEM_EXTERNAL_READY_URL to the Cloudflare HTTPS readiness URL")
    files = args.compose_file or ["compose.yaml", "compose.prod.yaml"]
    missing = [name for name in files if not Path(name).is_file()]
    if missing:
        parser.error(f"compose files not found: {', '.join(missing)}")
    compose = ["docker", "compose", "-p", args.project_name]
    for name in files:
        compose.extend(("-f", name))

    wait_ready(args.ready_url, args.timeout)
    database_name = current_database(compose)
    if not re.fullmatch(r"stage10_load_[a-z0-9_]+", database_name):
        parser.error("fault matrix refuses a database outside stage10_load_*")
    baseline = snapshot(compose)
    try:
        for sequence, service in enumerate(SERVICES, 1):
            print(f"FAULT stop {service}", flush=True)
            stopped = False
            probe_id = ""
            try:
                run([*compose, "stop", "--timeout", "10", service])
                stopped = True
                if service in {"backend", "frontend", "postgres"}:
                    wait_unavailable(args.ready_url)
                elif service == "cloudflared":
                    wait_ready(args.ready_url, args.timeout)
                    wait_unavailable(args.external_ready_url)
                else:
                    wait_ready(args.ready_url, args.timeout)
                if service in {"redis", "celery-worker"}:
                    probe_id = create_probe(
                        compose,
                        f"{args.project_name}-{sequence}-{int(time.time())}",
                    )
                elif service == "celery-beat":
                    wait_heartbeat_stale(compose, max(args.timeout, 75))
                elif service == "cloudflared":
                    snapshot(compose)
            finally:
                if stopped:
                    run([*compose, "up", "-d", service])
                    wait_running(compose, service, args.timeout)
                    wait_ready(args.ready_url, args.timeout)
                    if service == "cloudflared":
                        wait_ready(args.external_ready_url, args.timeout)
            if probe_id:
                verify_probe(compose, probe_id, args.timeout)
                baseline = snapshot(compose)
            verify(compose, baseline)
            print(f"RECOVERY {service}: PASS", flush=True)
    finally:
        subprocess.run([*compose, "up", "-d", "--wait"], check=False)
    print("Stage 10 fault matrix: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
