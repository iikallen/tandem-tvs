import os
import re
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email

from .base import *  # noqa: F403


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} is required in production")
    return value


def forbid_value(name: str, value: str, forbidden: set[str]) -> None:
    if value.casefold() in {item.casefold() for item in forbidden}:
        raise ImproperlyConfigured(f"{name} contains a development value")


def require_secret(name: str, value: str, minimum_length: int) -> None:
    normalized = value.casefold()
    placeholders = (
        "<",
        ">",
        "change-me",
        "changeme",
        "development",
        "django-insecure",
        "placeholder",
        "replace-me",
        "test-only",
    )
    if (
        len(value) < minimum_length
        or len(set(value)) < 5
        or any(marker in normalized for marker in placeholders)
    ):
        raise ImproperlyConfigured(f"{name} is weak or contains a placeholder value")


def bounded_integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ImproperlyConfigured(f"{name} must be between {minimum} and {maximum}")
    return value


def redis_target(name: str, url: str) -> tuple[str, int, int]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise ImproperlyConfigured(f"{name} must be a redis:// or rediss:// URL")
    query_db = parse_qs(parsed.query).get("db")
    raw_database = query_db[-1] if query_db else parsed.path.removeprefix("/") or "0"
    try:
        database = int(raw_database)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must select a numeric Redis database") from exc
    return parsed.hostname.lower(), parsed.port or 6379, database


DEBUG = False
SECRET_KEY = required("DJANGO_SECRET_KEY")
forbid_value(
    "DJANGO_SECRET_KEY",
    SECRET_KEY,
    {
        "development-only-change-me",
        "development-only-not-for-production",
    },
)
require_secret("DJANGO_SECRET_KEY", SECRET_KEY, 50)
ALLOWED_HOSTS = [
    *[host.strip() for host in required("DJANGO_ALLOWED_HOSTS").split(",") if host.strip()],
    "127.0.0.1",
]
if any(
    host in {"*", "localhost", "127.0.0.1"}
    or host.endswith((".invalid", ".example", ".test"))
    or "<" in host
    or ">" in host
    for host in ALLOWED_HOSTS[:-1]
):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS contains a development value")
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in required("DJANGO_CSRF_TRUSTED_ORIGINS").split(",")
]
if any(
    not origin.startswith("https://")
    or "localhost" in origin
    or (urlsplit(origin).hostname or "").endswith((".invalid", ".example", ".test"))
    for origin in CSRF_TRUSTED_ORIGINS
):
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS must contain production HTTPS origins")
if not os.getenv("DATABASE_URL"):
    for database_setting in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST"):
        required(database_setting)
database_password = str(DATABASES["default"].get("PASSWORD", ""))  # noqa: F405
forbid_value(
    "Production database password",
    database_password,
    {"", "tandem", "tandem-development-only", "replace-for-shared-environments"},
)
require_secret("Production database password", database_password, 16)
if postgres_password := os.getenv("POSTGRES_PASSWORD"):
    forbid_value(
        "POSTGRES_PASSWORD",
        postgres_password,
        {"tandem", "tandem-development-only", "replace-for-shared-environments"},
    )
    require_secret("POSTGRES_PASSWORD", postgres_password, 16)
POSTGRES_CONNECT_TIMEOUT_SECONDS = bounded_integer("POSTGRES_CONNECT_TIMEOUT_SECONDS", 5, 1, 30)
POSTGRES_STATEMENT_TIMEOUT_MS = bounded_integer(
    "POSTGRES_STATEMENT_TIMEOUT_MS", 15_000, 1_000, 120_000
)
production_database = cast(dict[str, Any], DATABASES["default"])  # noqa: F405
database_options = production_database.get("OPTIONS", {})
if not isinstance(database_options, dict):
    raise ImproperlyConfigured("Production database OPTIONS must be a mapping")
production_database["OPTIONS"] = database_options
database_options["connect_timeout"] = POSTGRES_CONNECT_TIMEOUT_SECONDS
existing_server_options = str(database_options.get("options", "")).strip()
database_options["options"] = (
    f"{existing_server_options} -c statement_timeout={POSTGRES_STATEMENT_TIMEOUT_MS}"
).strip()
REDIS_URL = required("REDIS_URL")
REALTIME_REDIS_URL = required("REALTIME_REDIS_URL")
CELERY_BROKER_URL = required("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = required("CELERY_RESULT_BACKEND")
cache_target = redis_target("REDIS_URL", REDIS_URL)
realtime_target = redis_target("REALTIME_REDIS_URL", REALTIME_REDIS_URL)
celery_broker_target = redis_target("CELERY_BROKER_URL", CELERY_BROKER_URL)
celery_result_target = redis_target("CELERY_RESULT_BACKEND", CELERY_RESULT_BACKEND)
if cache_target[2] != 0:
    raise ImproperlyConfigured("REDIS_URL must use logical Redis database 0")
if realtime_target[2] != 1:
    raise ImproperlyConfigured("REALTIME_REDIS_URL must use logical Redis database 1")
if cache_target == realtime_target:
    raise ImproperlyConfigured("REALTIME_REDIS_URL must be isolated from REDIS_URL")
if celery_broker_target[2] != 2 or celery_result_target[2] != 2:
    raise ImproperlyConfigured("Celery broker and result backend must use Redis database 2")
if celery_broker_target in {cache_target, realtime_target}:
    raise ImproperlyConfigured("CELERY_BROKER_URL must be isolated from cache and realtime")
REALTIME_ALLOWED_ORIGINS = [
    origin.strip() for origin in required("REALTIME_ALLOWED_ORIGINS").split(",") if origin.strip()
]
if not REALTIME_ALLOWED_ORIGINS:
    raise ImproperlyConfigured("REALTIME_ALLOWED_ORIGINS is required in production")
if any(not origin.startswith("https://") for origin in REALTIME_ALLOWED_ORIGINS):
    raise ImproperlyConfigured("REALTIME_ALLOWED_ORIGINS must contain HTTPS origins")
if any(
    (urlsplit(origin).hostname or "").endswith((".invalid", ".example", ".test"))
    for origin in REALTIME_ALLOWED_ORIGINS
):
    raise ImproperlyConfigured("REALTIME_ALLOWED_ORIGINS contains a development value")

AUTH_MODE = os.getenv("AUTH_MODE", "LOCAL_ONLY")
if AUTH_MODE != "LOCAL_ONLY":
    raise ImproperlyConfigured("Stage 6 production requires AUTH_MODE=LOCAL_ONLY")
AUTH_RECOVERY_MODE = required("AUTH_RECOVERY_MODE")
if AUTH_RECOVERY_MODE not in {"ADMIN_ONLY", "SMTP"}:
    raise ImproperlyConfigured("AUTH_RECOVERY_MODE must be ADMIN_ONLY or SMTP")
AUTH_PUBLIC_BASE_URL = os.getenv("AUTH_PUBLIC_BASE_URL", "")
if AUTH_RECOVERY_MODE == "SMTP":
    recovery_url = urlsplit(AUTH_PUBLIC_BASE_URL)
    if recovery_url.scheme != "https" or not recovery_url.hostname:
        raise ImproperlyConfigured(
            "AUTH_PUBLIC_BASE_URL must be an absolute HTTPS URL when AUTH_RECOVERY_MODE=SMTP"
        )
if WEB_PUSH_ENABLED:  # noqa: F405
    if not WEB_PUSH_ALLOWED_HOST_SUFFIXES:  # noqa: F405
        raise ImproperlyConfigured(
            "WEB_PUSH_ALLOWED_HOST_SUFFIXES is required when Web Push is enabled"
        )
    if not 1 <= WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER <= 20:  # noqa: F405
        raise ImproperlyConfigured("WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER must be between 1 and 20")
    VAPID_PUBLIC_KEY = required("VAPID_PUBLIC_KEY")
    VAPID_PRIVATE_KEY = required("VAPID_PRIVATE_KEY")
    require_secret("VAPID_PRIVATE_KEY", VAPID_PRIVATE_KEY, 32)
    VAPID_SUBJECT = required("VAPID_SUBJECT")
    if not (VAPID_SUBJECT.startswith("mailto:") or VAPID_SUBJECT.startswith("https://")):
        raise ImproperlyConfigured("VAPID_SUBJECT must be a mailto: or HTTPS URI")
    if VAPID_SUBJECT.endswith("example.invalid"):
        raise ImproperlyConfigured("VAPID_SUBJECT contains a development value")
if AUTH_RECOVERY_MODE == "SMTP" or NOTIFICATION_EMAIL_ENABLED:  # noqa: F405
    DEFAULT_FROM_EMAIL = required("DEFAULT_FROM_EMAIL")
    EMAIL_HOST = required("EMAIL_HOST")
    try:
        validate_email(DEFAULT_FROM_EMAIL)
    except ValidationError as exc:
        raise ImproperlyConfigured("DEFAULT_FROM_EMAIL must be a valid email address") from exc
    if (
        DEFAULT_FROM_EMAIL.endswith("example.invalid")
        or EMAIL_HOST.casefold() in {"localhost", "127.0.0.1", "::1"}
        or EMAIL_HOST.endswith(".invalid")
    ):
        raise ImproperlyConfigured("Email configuration contains a development value")
    if EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":  # noqa: F405
        raise ImproperlyConfigured("SMTP features require Django's SMTP email backend")
    if not 1 <= EMAIL_PORT <= 65_535:  # noqa: F405
        raise ImproperlyConfigured("EMAIL_PORT must be between 1 and 65535")
    if bool(EMAIL_HOST_USER) != bool(EMAIL_HOST_PASSWORD):  # noqa: F405
        raise ImproperlyConfigured("EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be set together")
    if EMAIL_HOST_PASSWORD:  # noqa: F405
        require_secret("EMAIL_HOST_PASSWORD", EMAIL_HOST_PASSWORD, 12)  # noqa: F405
ALLOW_BOOTSTRAP_LOCAL_ADMIN = environment_bool(  # noqa: F405
    "ALLOW_BOOTSTRAP_LOCAL_ADMIN", False
)
if ALLOW_BOOTSTRAP_LOCAL_ADMIN:
    raise ImproperlyConfigured("ALLOW_BOOTSTRAP_LOCAL_ADMIN is forbidden in production")
if os.getenv("STAGE6_DEMO_PASSWORD", "").strip():
    raise ImproperlyConfigured("STAGE6_DEMO_PASSWORD is forbidden in production")
PORTAL_ADAPTER = os.getenv("PORTAL_ADAPTER", "unavailable")
ALLOW_MOCK_PORTAL_ADAPTER = False
if PORTAL_ADAPTER != "unavailable":
    raise ImproperlyConfigured("Production requires PORTAL_ADAPTER=unavailable")

APP_VERSION = required("APP_VERSION")
APP_GIT_SHA = required("APP_GIT_SHA")
if not re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION):
    raise ImproperlyConfigured("APP_VERSION must be a semantic version")
if not re.fullmatch(r"[0-9a-f]{40}", APP_GIT_SHA):
    raise ImproperlyConfigured("APP_GIT_SHA must be a full lowercase Git commit SHA")
OPS_MONITORING_TOKEN = required("OPS_MONITORING_TOKEN")
require_secret("OPS_MONITORING_TOKEN", OPS_MONITORING_TOKEN, 32)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "__Host-tandem_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "apps.core.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
