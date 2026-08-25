#!/usr/bin/env python3
import argparse
import json
import os
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
    parser.add_argument(
        "--ready-url",
        default=os.environ.get("TANDEM_READY_URL", "http://localhost:8080/api/v1/health/ready"),
    )
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if os.environ.get("FAULT_TEST_CONFIRMATION") != "isolated-environment":
        parser.error("set FAULT_TEST_CONFIRMATION=isolated-environment")
    files = args.compose_file or ["compose.yaml", "compose.prod.yaml"]
    missing = [name for name in files if not Path(name).is_file()]
    if missing:
        parser.error(f"compose files not found: {', '.join(missing)}")
    compose = ["docker", "compose"]
    for name in files:
        compose.extend(("-f", name))

    wait_ready(args.ready_url, args.timeout)
    baseline = snapshot(compose)
    for service in SERVICES:
        print(f"FAULT stop {service}", flush=True)
        run([*compose, "stop", "--timeout", "10", service])
        run([*compose, "up", "-d", service])
        wait_running(compose, service, args.timeout)
        wait_ready(args.ready_url, args.timeout)
        verify(compose, baseline)
        print(f"RECOVERY {service}: PASS", flush=True)
    print("Stage 10 fault matrix: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
