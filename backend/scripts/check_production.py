import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

if not __debug__:
    raise SystemExit("Production preflight must run without Python optimization (-O)")

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PRODUCTION_SETTINGS = "config.settings.production"


def fail(message: str) -> None:
    raise SystemExit(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


configured_settings = os.getenv("DJANGO_SETTINGS_MODULE")
require(
    configured_settings in {None, "", PRODUCTION_SETTINGS},
    "DJANGO_SETTINGS_MODULE must be config.settings.production for production preflight",
)
os.environ["DJANGO_SETTINGS_MODULE"] = PRODUCTION_SETTINGS
os.environ.pop("PYTHONOPTIMIZE", None)

tunnel_token = os.getenv("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
placeholder_markers = ("<", ">", "change-me", "changeme", "development", "placeholder")
require(
    len(tunnel_token) >= 32
    and len(set(tunnel_token)) >= 5
    and not any(marker in tunnel_token.casefold() for marker in placeholder_markers),
    "CLOUDFLARE_TUNNEL_TOKEN is missing, weak or contains a placeholder value",
)

sys.path.insert(0, str(BACKEND))
import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402

from apps.identity.portal import get_portal_adapter  # noqa: E402

call_command("check")
call_command("check", "--deploy", "--tag", "security", "--fail-level", "WARNING")
runtime_requirements = {
    "DEBUG must be false": settings.DEBUG is False,
    "secure session cookies must be enabled": settings.SESSION_COOKIE_SECURE,
    "secure CSRF cookies must be enabled": settings.CSRF_COOKIE_SECURE,
    "HTTPS redirect must be enabled": settings.SECURE_SSL_REDIRECT,
    "HSTS must be at least one year": settings.SECURE_HSTS_SECONDS >= 31_536_000,
    "AUTH_MODE must be LOCAL_ONLY": settings.AUTH_MODE == "LOCAL_ONLY",
    "PORTAL_ADAPTER must be unavailable": settings.PORTAL_ADAPTER == "unavailable",
    "bootstrap local admin must be disabled": not settings.ALLOW_BOOTSTRAP_LOCAL_ADMIN,
    "API documentation must be disabled": not settings.API_DOCS_ENABLED,
    "USE_X_FORWARDED_HOST must be disabled": not settings.USE_X_FORWARDED_HOST,
}
for description, valid in runtime_requirements.items():
    require(valid, f"Production runtime check failed: {description}")
get_portal_adapter()

release = subprocess.run(
    ["git", "rev-parse", "HEAD"],
    cwd=ROOT,
    capture_output=True,
    text=True,
    check=False,
)
require(release.returncode == 0, "Unable to resolve the current Git commit")
require(
    release.stdout.strip() == settings.APP_GIT_SHA,
    "APP_GIT_SHA must match the current Git commit",
)

compose_environment = os.environ.copy()
compose_environment.pop("PYTHONOPTIMIZE", None)
compose = subprocess.run(
    [
        "docker",
        "compose",
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(ROOT / "compose.prod.yaml"),
        "config",
        "--format",
        "json",
    ],
    env=compose_environment,
    capture_output=True,
    text=True,
    check=False,
)
if compose.returncode:
    sys.stderr.write(compose.stderr)
    raise SystemExit(compose.returncode)

active = subprocess.run(
    [
        "docker",
        "compose",
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(ROOT / "compose.prod.yaml"),
        "config",
        "--services",
    ],
    env=compose_environment,
    capture_output=True,
    text=True,
    check=False,
)
if active.returncode:
    sys.stderr.write(active.stderr)
    raise SystemExit(active.returncode)
expected_services = {
    "postgres",
    "redis",
    "migrate",
    "backend",
    "celery-worker",
    "celery-beat",
    "frontend",
    "cloudflared",
}
require(
    set(active.stdout.splitlines()) == expected_services,
    "Production Compose active service list is incomplete or unexpected",
)

try:
    rendered: dict[str, Any] = json.loads(compose.stdout)
except json.JSONDecodeError as exc:
    fail(f"Production Compose did not return valid JSON: {exc}")

services = rendered.get("services", {})
require(isinstance(services, dict), "Production Compose has no services mapping")
cloudflared = services.get("cloudflared", {})
require(isinstance(cloudflared, dict), "Production Compose must include cloudflared")
require(not cloudflared.get("profiles"), "Production cloudflared must not require a profile")
postgres = services.get("postgres", {})
require(
    isinstance(postgres, dict)
    and postgres.get("image") == f"tandem-tvs-postgres:{settings.APP_GIT_SHA}",
    "Production PostgreSQL image must be tagged with APP_GIT_SHA",
)
for service_name, image_name in (
    ("backend", "tandem-tvs-backend"),
    ("frontend", "tandem-tvs-frontend"),
):
    service = services.get(service_name, {})
    require(
        isinstance(service, dict)
        and service.get("image") == f"{image_name}:{settings.APP_GIT_SHA}",
        f"Production {service_name} image must be tagged with APP_GIT_SHA",
    )
backend = services.get("backend", {})
healthcheck = backend.get("healthcheck", {}) if isinstance(backend, dict) else {}
require(
    healthcheck.get("timeout") == "5s",
    "Backend container healthcheck must have a five-second timeout",
)

for service_name in ("migrate", "backend", "celery-worker", "celery-beat"):
    service = services.get(service_name, {})
    environment = service.get("environment", {}) if isinstance(service, dict) else {}
    require(
        environment.get("DJANGO_SETTINGS_MODULE") == PRODUCTION_SETTINGS,
        f"{service_name} must use production Django settings",
    )

for service_name in expected_services:
    service = services.get(service_name, {})
    logging = service.get("logging", {}) if isinstance(service, dict) else {}
    options = logging.get("options", {}) if isinstance(logging, dict) else {}
    require(
        logging.get("driver") == "json-file"
        and options.get("max-size") == "10m"
        and options.get("max-file") == "5",
        f"{service_name} must use bounded json-file logging",
    )

for forbidden in (
    "development-only",
    "Tandem development passphrase",
    '"PORTAL_ADAPTER":"mock"',
):
    require(forbidden not in compose.stdout, f"Production Compose contains {forbidden}")

print("Production preflight: PASS")
