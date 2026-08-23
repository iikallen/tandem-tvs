import os
import subprocess
import sys

environment = os.environ | {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": "check-only-not-a-deployment-secret-with-sufficient-length-123456",
    "DJANGO_ALLOWED_HOSTS": "portal.example.invalid",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://portal.example.invalid",
    "DATABASE_URL": "postgresql://check:check@postgres:5432/check",
    "REDIS_URL": "redis://redis:6379/0",
    "PORTAL_ADAPTER": "contract-pending",
}

raise SystemExit(
    subprocess.call(
        [sys.executable, "manage.py", "check", "--deploy"],
        env=environment,
    )
)
