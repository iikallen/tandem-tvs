import os
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} is required in production")
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
ALLOWED_HOSTS = [
    *[host.strip() for host in required("DJANGO_ALLOWED_HOSTS").split(",") if host.strip()],
    "127.0.0.1",
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in required("DJANGO_CSRF_TRUSTED_ORIGINS").split(",")
]
if not os.getenv("DATABASE_URL"):
    for database_setting in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST"):
        required(database_setting)
REDIS_URL = required("REDIS_URL")
REALTIME_REDIS_URL = required("REALTIME_REDIS_URL")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/2")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
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

AUTH_MODE = os.getenv("AUTH_MODE", "LOCAL_ONLY")
if AUTH_MODE != "LOCAL_ONLY":
    raise ImproperlyConfigured("Stage 6 production requires AUTH_MODE=LOCAL_ONLY")
AUTH_RECOVERY_MODE = os.getenv("AUTH_RECOVERY_MODE", "ADMIN_ONLY")
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
    VAPID_SUBJECT = required("VAPID_SUBJECT")
    if not (VAPID_SUBJECT.startswith("mailto:") or VAPID_SUBJECT.startswith("https://")):
        raise ImproperlyConfigured("VAPID_SUBJECT must be a mailto: or HTTPS URI")
if NOTIFICATION_EMAIL_ENABLED:  # noqa: F405
    DEFAULT_FROM_EMAIL = required("DEFAULT_FROM_EMAIL")
    EMAIL_HOST = required("EMAIL_HOST")
ALLOW_BOOTSTRAP_LOCAL_ADMIN = os.getenv("ALLOW_BOOTSTRAP_LOCAL_ADMIN", "false").lower() == "true"
PORTAL_ADAPTER = os.getenv("PORTAL_ADAPTER", "unavailable")
ALLOW_MOCK_PORTAL_ADAPTER = False
if PORTAL_ADAPTER == "mock":
    raise ImproperlyConfigured("MockPortalAdapter is forbidden in production")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
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
