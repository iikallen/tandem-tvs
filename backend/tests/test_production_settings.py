import os
import subprocess
import sys
from pathlib import Path


def production_environment(**overrides: str) -> dict[str, str]:
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "production-check-secret-with-enough-entropy",
        "DJANGO_ALLOWED_HOSTS": "portal.example.com",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://portal.example.com",
        "DATABASE_URL": "postgresql://check:safe-production-password@postgres:5432/check",
        "POSTGRES_PASSWORD": "safe-production-password",
        "REDIS_URL": "redis://redis:6379/0",
        "REALTIME_REDIS_URL": "redis://redis:6379/1",
        "REALTIME_ALLOWED_ORIGINS": "https://portal.example.com",
        "CELERY_BROKER_URL": "redis://redis:6379/2",
        "CELERY_RESULT_BACKEND": "redis://redis:6379/2",
        "AUTH_RECOVERY_MODE": "ADMIN_ONLY",
        "AUTH_PUBLIC_BASE_URL": "https://portal.example.com",
        "PORTAL_ADAPTER": "unavailable",
        "ALLOW_BOOTSTRAP_LOCAL_ADMIN": "false",
        "STAGE6_DEMO_PASSWORD": "",
        "WEB_PUSH_ENABLED": "false",
        "NOTIFICATION_EMAIL_ENABLED": "false",
        "APP_VERSION": "1.0.0",
        "APP_GIT_SHA": "a" * 40,
        "OPS_MONITORING_TOKEN": "stage10-monitoring-token-32-chars",
    }
    environment.update(overrides)
    return environment


def run_manage(*arguments: str, environment: dict[str, str]):
    return subprocess.run(
        [sys.executable, "manage.py", *arguments],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_production_settings_reject_mock_adapter():
    result = run_manage("check", environment=production_environment(PORTAL_ADAPTER="mock"))
    assert result.returncode != 0
    assert "Production requires PORTAL_ADAPTER=unavailable" in result.stderr


def test_production_does_not_expose_api_documentation():
    result = run_manage(
        "shell",
        "-c",
        "from django.urls import get_resolver; "
        "print(sorted(name for name in get_resolver().reverse_dict if isinstance(name, str)))",
        environment=production_environment(),
    )

    assert result.returncode == 0
    assert "api-docs" not in result.stdout
    assert "schema" not in result.stdout


def test_runtime_limits_websocket_frames_before_application_buffering():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()

    assert '"--ws-max-size", "512"' in dockerfile
    assert '"--no-access-log"' in dockerfile


def test_production_requires_an_isolated_realtime_redis_database():
    environment = production_environment(REALTIME_REDIS_URL="redis://redis/0")
    result = run_manage(
        "check",
        environment=environment,
    )

    assert result.returncode != 0
    assert "REALTIME_REDIS_URL must use logical Redis database 1" in result.stderr

    environment["REALTIME_REDIS_URL"] = "redis://redis:6379/2"
    result = run_manage("check", environment=environment)
    assert result.returncode != 0
    assert "REALTIME_REDIS_URL must use logical Redis database 1" in result.stderr


def test_production_requires_an_isolated_celery_redis_database():
    result = run_manage(
        "check",
        environment=production_environment(CELERY_BROKER_URL="redis://redis:6379/0"),
    )
    assert result.returncode != 0
    assert "Celery broker and result backend must use Redis database 2" in result.stderr


def test_production_smtp_recovery_requires_absolute_https_public_url():
    environment = production_environment(
        AUTH_RECOVERY_MODE="SMTP",
        AUTH_PUBLIC_BASE_URL="http://portal.example.com",
    )
    result = run_manage("check", environment=environment)
    assert result.returncode != 0
    assert "AUTH_PUBLIC_BASE_URL must be an absolute HTTPS URL" in result.stderr

    environment["AUTH_PUBLIC_BASE_URL"] = "https://portal.example.com"
    result = run_manage("check", environment=environment)
    assert result.returncode == 0


def test_production_push_requires_complete_vapid_configuration():
    environment = production_environment(
        WEB_PUSH_ENABLED="true",
        VAPID_PUBLIC_KEY="public",
        VAPID_PRIVATE_KEY="",
        VAPID_SUBJECT="mailto:security@portal.example.com",
    )
    result = run_manage("check", environment=environment)
    assert result.returncode != 0
    assert "VAPID_PRIVATE_KEY is required in production" in result.stderr

    environment["VAPID_PRIVATE_KEY"] = "private"
    result = run_manage("check", environment=environment)
    assert result.returncode == 0


def test_compose_celery_healthchecks_are_targeted_and_heartbeat_based():
    compose = (Path(__file__).resolve().parents[2] / "compose.yaml").read_text()

    assert "inspect ping --destination celery@$$HOSTNAME --timeout 5" in compose
    assert "tandem:celery:reconcile-heartbeat" in compose
    assert "time.time()-heartbeat < 60" in compose
    assert "interval: 15s" in compose
    assert "start_period: 45s" in compose


def test_cloudflare_client_ip_is_trusted_only_on_dedicated_tunnel_network():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "compose.yaml").read_text()
    nginx = (root / "frontend" / "infra" / "nginx.conf").read_text()

    assert "172.31.250.0/29" in compose
    assert "172.31.250.0/29 1;" in nginx
    assert "172.16.0.0/12 1;" not in nginx
    assert "~^1:(.+)$ $1;" in nginx
