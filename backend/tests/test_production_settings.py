import os
import subprocess
import sys
from pathlib import Path


def test_production_settings_reject_mock_adapter():
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "test-only-production-check",
        "DJANGO_ALLOWED_HOSTS": "portal.example.invalid",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://portal.example.invalid",
        "DATABASE_URL": "postgresql://check:check@postgres:5432/check",
        "REDIS_URL": "redis://redis:6379/0",
        "PORTAL_ADAPTER": "mock",
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "MockPortalAdapter is forbidden in production" in result.stderr


def test_production_does_not_expose_api_documentation():
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "test-only-production-check",
        "DJANGO_ALLOWED_HOSTS": "portal.example.invalid",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://portal.example.invalid",
        "DATABASE_URL": "postgresql://check:check@postgres:5432/check",
        "REDIS_URL": "redis://redis:6379/0",
        "PORTAL_ADAPTER": "unavailable",
    }
    result = subprocess.run(
        [
            sys.executable,
            "manage.py",
            "shell",
            "-c",
            "from django.urls import get_resolver; "
            "print(sorted(name for name in get_resolver().reverse_dict if isinstance(name, str)))",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "api-docs" not in result.stdout
    assert "schema" not in result.stdout
