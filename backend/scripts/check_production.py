import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

environment = os.environ | {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": "check-only-not-a-deployment-secret-with-sufficient-length-123456",
    "DJANGO_ALLOWED_HOSTS": "portal.example.invalid",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://portal.example.invalid",
    "DATABASE_URL": "postgresql://check:check@postgres:5432/check",
    "REDIS_URL": "redis://redis:6379/0",
    "REALTIME_REDIS_URL": "redis://redis:6379/1",
    "CELERY_BROKER_URL": "redis://redis:6379/2",
    "CELERY_RESULT_BACKEND": "redis://redis:6379/2",
    "REALTIME_ALLOWED_ORIGINS": "https://portal.example.invalid",
    "PORTAL_ADAPTER": "unavailable",
    "POSTGRES_DB": "check",
    "POSTGRES_USER": "check",
    "POSTGRES_PASSWORD": "production-check-database-password",
    "ALLOW_BOOTSTRAP_LOCAL_ADMIN": "false",
    "STAGE6_DEMO_PASSWORD": "",
    "APP_VERSION": "1.0.0",
    "APP_GIT_SHA": "0123456789abcdef0123456789abcdef01234567",
    "OPS_MONITORING_TOKEN": "production-check-only-monitoring-token",
    "AUTH_RECOVERY_MODE": "ADMIN_ONLY",
    "AUTH_PUBLIC_BASE_URL": "https://portal.example.invalid",
    "WEB_PUSH_ENABLED": "false",
    "NOTIFICATION_EMAIL_ENABLED": "false",
    "CLOUDFLARE_TUNNEL_TOKEN": "production-check-only-tunnel-token",
}

commands = (
    [sys.executable, "manage.py", "check", "--deploy"],
    [
        sys.executable,
        "manage.py",
        "shell",
        "-c",
        "from django.conf import settings; "
        "from apps.identity.portal import get_portal_adapter; "
        "assert settings.DEBUG is False; "
        "assert settings.SESSION_COOKIE_SECURE; "
        "assert settings.CSRF_COOKIE_SECURE; "
        "assert settings.SECURE_SSL_REDIRECT; "
        "assert settings.SECURE_HSTS_SECONDS >= 31536000; "
        "assert settings.AUTH_MODE == 'LOCAL_ONLY'; "
        "assert settings.PORTAL_ADAPTER == 'unavailable'; "
        "assert not settings.ALLOW_BOOTSTRAP_LOCAL_ADMIN; "
        "assert not settings.API_DOCS_ENABLED; "
        "assert settings.APP_VERSION == '1.0.0'; "
        "assert len(settings.APP_GIT_SHA) == 40; "
        "get_portal_adapter()",
    ],
)

for command in commands:
    if return_code := subprocess.call(command, env=environment):
        raise SystemExit(return_code)

compose = subprocess.run(
    [
        "docker",
        "compose",
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(ROOT / "compose.prod.yaml"),
        "config",
    ],
    env=environment,
    capture_output=True,
    text=True,
    check=False,
)
if compose.returncode:
    sys.stderr.write(compose.stderr)
    raise SystemExit(compose.returncode)
for forbidden in (
    "development-only",
    "Tandem development passphrase",
    "PORTAL_ADAPTER: mock",
):
    if forbidden in compose.stdout:
        raise SystemExit(f"Production Compose contains forbidden value: {forbidden}")
