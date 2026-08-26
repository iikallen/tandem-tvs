import copy
import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast


def production_environment(**overrides: str) -> dict[str, str]:
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "9r!V2x#Q7m@L4p$W8s%Y3n^K6d&F1h*J5c+B0t-Z_e=U?i:Aq7#N",
        "DJANGO_ALLOWED_HOSTS": "portal.company.kz",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://portal.company.kz",
        "DATABASE_URL": "postgresql://check:safe-production-password@postgres:5432/check",
        "POSTGRES_PASSWORD": "safe-production-password",
        "REDIS_URL": "redis://redis:6379/0",
        "REALTIME_REDIS_URL": "redis://redis:6379/1",
        "REALTIME_ALLOWED_ORIGINS": "https://portal.company.kz",
        "CELERY_BROKER_URL": "redis://redis:6379/2",
        "CELERY_RESULT_BACKEND": "redis://redis:6379/2",
        "AUTH_RECOVERY_MODE": "ADMIN_ONLY",
        "AUTH_PUBLIC_BASE_URL": "https://portal.company.kz",
        "PORTAL_ADAPTER": "unavailable",
        "ALLOW_BOOTSTRAP_LOCAL_ADMIN": "false",
        "STAGE6_DEMO_PASSWORD": "",
        "WEB_PUSH_ENABLED": "false",
        "NOTIFICATION_EMAIL_ENABLED": "false",
        "APP_VERSION": "1.0.0",
        "APP_GIT_SHA": "a" * 40,
        "OPS_MONITORING_TOKEN": "N7q!2Vx#9Lm@4Rp$8Tz%6Wc&3Ky*5Hd+",
        "CLOUDFLARE_TUNNEL_TOKEN": "eyJhbGciOiJIUzI1NiJ9.production.signature-token",
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


def test_production_settings_load_with_complete_operator_configuration(monkeypatch):
    from config.settings import base

    environment = production_environment()
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    database = copy.deepcopy(base.DATABASES)
    database["default"]["PASSWORD"] = "safe-production-password"
    monkeypatch.setattr(base, "DATABASES", database)
    sys.modules.pop("config.settings.production", None)
    try:
        production = importlib.import_module("config.settings.production")
        assert production.DEBUG is False
        assert production.PORTAL_ADAPTER == "unavailable"
        assert production.DATABASES["default"]["OPTIONS"] == {
            "connect_timeout": 5,
            "options": "-c statement_timeout=15000",
        }
        assert production.DATABASES["default"]["CONN_MAX_AGE"] == 0
        channel_host = cast(Any, production.CHANNEL_LAYERS)["default"]["CONFIG"]["hosts"][0]
        assert channel_host["socket_connect_timeout"] == 1
        assert "socket_timeout" not in channel_host
        assert production.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == [
            "rest_framework.renderers.JSONRenderer"
        ]
        assert production.REALTIME_SOCKET_LIFETIME_SECONDS == 1_200
        assert production.REALTIME_SOCKET_LEASE_SECONDS == 1_230
        assert production.USE_X_FORWARDED_HOST is False
    finally:
        sys.modules.pop("config.settings.production", None)


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
    assert '"--workers", "4"' in dockerfile
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


def test_production_socket_lifetime_covers_capacity_ramp_and_hold():
    result = run_manage(
        "check",
        environment=production_environment(REALTIME_SOCKET_LIFETIME_SECONDS="900"),
    )

    assert result.returncode != 0
    assert "REALTIME_SOCKET_LIFETIME_SECONDS must be between 1080 and 43200" in result.stderr


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
        AUTH_PUBLIC_BASE_URL="http://portal.company.kz",
    )
    result = run_manage("check", environment=environment)
    assert result.returncode != 0
    assert "AUTH_PUBLIC_BASE_URL must be an absolute HTTPS URL" in result.stderr

    environment.update(
        AUTH_PUBLIC_BASE_URL="https://portal.company.kz",
        DEFAULT_FROM_EMAIL="tandem@company.kz",
        EMAIL_HOST="smtp.internal.company.kz",
    )
    result = run_manage("check", environment=environment)
    assert result.returncode == 0


def test_production_rejects_unknown_recovery_mode():
    result = run_manage(
        "check",
        environment=production_environment(AUTH_RECOVERY_MODE="DISABLED"),
    )

    assert result.returncode != 0
    assert "AUTH_RECOVERY_MODE must be ADMIN_ONLY or SMTP" in result.stderr


def test_production_requires_smtp_for_notification_email():
    result = run_manage(
        "check",
        environment=production_environment(NOTIFICATION_EMAIL_ENABLED="true"),
    )
    assert result.returncode != 0
    assert "DEFAULT_FROM_EMAIL is required in production" in result.stderr

    result = run_manage(
        "check",
        environment=production_environment(
            NOTIFICATION_EMAIL_ENABLED="true",
            DEFAULT_FROM_EMAIL="tandem@company.kz",
            EMAIL_HOST="smtp.internal.company.kz",
        ),
    )
    assert result.returncode == 0


def test_production_rejects_invalid_boolean_values():
    for name in (
        "ALLOW_BOOTSTRAP_LOCAL_ADMIN",
        "API_DOCS_ENABLED",
        "EMAIL_USE_TLS",
        "NOTIFICATION_EMAIL_ENABLED",
        "WEB_PUSH_ENABLED",
    ):
        result = run_manage("check", environment=production_environment(**{name: "tru"}))
        assert result.returncode != 0
        assert f"{name} must be true or false" in result.stderr


def test_production_rejects_weak_or_placeholder_secrets():
    for name, value in (
        ("DJANGO_SECRET_KEY", "change-me"),
        ("POSTGRES_PASSWORD", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        ("OPS_MONITORING_TOKEN", "placeholder-monitoring-token-123456789"),
    ):
        environment = production_environment(**{name: value})
        if name == "POSTGRES_PASSWORD":
            environment["DATABASE_URL"] = f"postgresql://check:{value}@postgres:5432/check"
        result = run_manage("check", environment=environment)
        assert result.returncode != 0
        assert "weak or contains a placeholder value" in result.stderr


def test_production_disables_forwarded_host_and_bounds_database_waits():
    result = run_manage(
        "shell",
        "-c",
        "from django.conf import settings; "
        "print(settings.USE_X_FORWARDED_HOST, settings.DATABASES['default']['OPTIONS'])",
        environment=production_environment(),
    )

    assert result.returncode == 0
    assert "False" in result.stdout
    assert "'connect_timeout': 5" in result.stdout
    assert "statement_timeout=15000" in result.stdout


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

    environment["VAPID_PRIVATE_KEY"] = "M7v!2Pq#9Lx@4Rc$8Tz%6Wk&3Hy*5Nd+"
    result = run_manage("check", environment=environment)
    assert result.returncode == 0


def test_compose_celery_healthchecks_are_targeted_and_heartbeat_based():
    compose = (Path(__file__).resolve().parents[2] / "compose.yaml").read_text()

    assert "inspect ping --destination celery@$$HOSTNAME --timeout 5" in compose
    assert "tandem:celery:reconcile-heartbeat" in compose
    assert "time.time()-heartbeat < 60" in compose


def test_backend_healthcheck_uses_the_configured_allowed_host():
    compose = (Path(__file__).resolve().parents[2] / "compose.yaml").read_text()

    assert "host=os.environ.get('DJANGO_ALLOWED_HOSTS','localhost')" in compose
    assert "headers={'Host': host, 'X-Forwarded-Proto': 'https'}" in compose
    assert "interval: 15s" in compose
    assert "start_period: 45s" in compose


def test_cloudflare_client_ip_is_trusted_only_on_dedicated_tunnel_network():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "compose.yaml").read_text()
    nginx = (root / "frontend" / "infra" / "nginx.conf").read_text()

    assert "172.31.250.0/29" in compose
    assert "172.31.251.0/29" in compose
    assert "172.31.250.0/29 1;" in nginx
    assert "172.16.0.0/12 1;" not in nginx
    assert "~^1:(.+)$ $1;" in nginx


def test_proxy_headers_are_overwritten_and_uvicorn_trust_is_network_scoped():
    root = Path(__file__).resolve().parents[2]
    nginx = (root / "frontend" / "infra" / "nginx.conf").read_text()
    dockerfile = (root / "backend" / "Dockerfile").read_text()

    assert "$proxy_add_x_forwarded_for" not in nginx
    assert "default $http_x_forwarded_proto" not in nginx
    assert 'proxy_set_header X-Forwarded-Host "";' in nginx
    assert 'proxy_set_header Forwarded "";' in nginx
    assert "--forwarded-allow-ips=*" not in dockerfile
    assert "--forwarded-allow-ips=127.0.0.1,172.31.251.0/29" in dockerfile


def test_production_compose_activates_tunnel_and_bounds_logs():
    root = Path(__file__).resolve().parents[2]
    production = (root / "compose.prod.yaml").read_text()

    assert "profiles: !reset []" in production
    assert "tandem-tvs-postgres:${APP_GIT_SHA" in production
    assert "max_connections=${POSTGRES_MAX_CONNECTIONS:-400}" in production
    assert production.count("logging: *production-logging") == 8


def test_stage10_runtime_verifier_only_runs_in_production_compose():
    makefile = (Path(__file__).resolve().parents[2] / "Makefile").read_text()

    assert '"$$DJANGO_SETTINGS_MODULE" = "config.settings.production"' in makefile
    assert "Stage 10 runtime verification deferred to production-shaped Compose" in makefile


def test_acceptance_scripts_reject_optimized_python():
    backend = Path(__file__).resolve().parents[1]
    for script in ("check_production.py", "verify_stage10.py"):
        result = subprocess.run(
            [sys.executable, "-O", str(backend / "scripts" / script)],
            cwd=backend,
            env=production_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "without Python optimization (-O)" in result.stderr


def test_acceptance_scripts_use_explicit_production_checks():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    preflight = (scripts / "check_production.py").read_text()
    verifier = (scripts / "verify_stage10.py").read_text()

    assert "assert " not in preflight
    assert "assert " not in verifier
    assert 'PRODUCTION_SETTINGS = "config.settings.production"' in verifier
    assert "http.client.HTTPConnection" in verifier
    assert '"--tag", "security", "--fail-level", "WARNING"' in preflight


def test_production_preflight_uses_current_operator_secrets():
    backend = Path(__file__).resolve().parents[1]
    environment = production_environment()
    environment.pop("DJANGO_SECRET_KEY")

    result = subprocess.run(
        [sys.executable, str(backend / "scripts" / "check_production.py")],
        cwd=backend,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY is required in production" in result.stderr
