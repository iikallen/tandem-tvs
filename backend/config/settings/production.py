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
cache_target = redis_target("REDIS_URL", REDIS_URL)
realtime_target = redis_target("REALTIME_REDIS_URL", REALTIME_REDIS_URL)
if cache_target[2] != 0:
    raise ImproperlyConfigured("REDIS_URL must use logical Redis database 0")
if realtime_target[2] != 1:
    raise ImproperlyConfigured("REALTIME_REDIS_URL must use logical Redis database 1")
if cache_target == realtime_target:
    raise ImproperlyConfigured("REALTIME_REDIS_URL must be isolated from REDIS_URL")
REALTIME_ALLOWED_ORIGINS = [
    origin.strip() for origin in required("REALTIME_ALLOWED_ORIGINS").split(",") if origin.strip()
]
if not REALTIME_ALLOWED_ORIGINS:
    raise ImproperlyConfigured("REALTIME_ALLOWED_ORIGINS is required in production")

PORTAL_ADAPTER = required("PORTAL_ADAPTER")
ALLOW_MOCK_PORTAL_ADAPTER = False
if PORTAL_ADAPTER == "mock":
    raise ImproperlyConfigured("MockPortalAdapter is forbidden in production")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
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
