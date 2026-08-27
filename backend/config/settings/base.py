import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]
APP_VERSION = os.getenv("APP_VERSION", "development")
APP_GIT_SHA = os.getenv("APP_GIT_SHA", "unknown")


def environment_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, str(default)).strip().casefold()
    if raw_value not in {"true", "false"}:
        raise ImproperlyConfigured(f"{name} must be true or false")
    return raw_value == "true"


SECRET_KEY: str = "development-only-not-for-production"
DEBUG: bool = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "channels",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "apps.core",
    "apps.identity",
    "apps.organization",
    "apps.publications",
    "apps.discussions",
    "apps.realtime",
    "apps.messenger",
    "apps.notifications",
    "apps.search",
    "apps.ops",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.ops.metrics.MetricsMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.identity.middleware.AuthSessionExpiryMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "tandem-stage1",
    },
    "throttles": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "tandem-sessions",
    },
}


def postgres_config(
    *,
    name: str,
    user: str,
    password: str,
    host: str,
    port: str,
    options: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": user,
        "PASSWORD": password,
        "HOST": host,
        "PORT": port,
        "CONN_MAX_AGE": 60,
        "OPTIONS": options or {},
    }


def database_config(database_url: str) -> dict[str, object]:
    parsed_database = urlparse(database_url)
    return postgres_config(
        name=unquote(parsed_database.path.lstrip("/")),
        user=unquote(parsed_database.username or ""),
        password=unquote(parsed_database.password or ""),
        host=parsed_database.hostname or "",
        port=str(parsed_database.port or 5432),
        options=dict(parse_qsl(parsed_database.query, keep_blank_values=True)),
    )


if database_url := os.getenv("DATABASE_URL"):
    DATABASES = {"default": database_config(database_url)}
elif postgres_host := os.getenv("POSTGRES_HOST"):
    DATABASES = {
        "default": postgres_config(
            name=os.getenv("POSTGRES_DB", ""),
            user=os.getenv("POSTGRES_USER", ""),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            host=postgres_host,
            port=os.getenv("POSTGRES_PORT", "5432"),
        )
    }

if redis_url := os.getenv("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": redis_url,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "SOCKET_CONNECT_TIMEOUT": 1,
                "SOCKET_TIMEOUT": 1,
            },
        },
        "throttles": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "tandem-throttles",
        },
    }

LANGUAGE_CODE = "ru"
TIME_ZONE = "Asia/Qyzylorda"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "identity.User"
AUTHENTICATION_BACKENDS = ["apps.identity.backends.CaseInsensitiveModelBackend"]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 15},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "apps.identity.validators.LocalPasswordBlocklistValidator"},
]
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME: str = "tandem_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_AGE = int(os.getenv("AUTH_SESSION_MAX_AGE_SECONDS", "43200"))
AUTH_SESSION_MAX_AGE_SECONDS = SESSION_COOKIE_AGE
AUTH_SESSION_IDLE_SECONDS = int(os.getenv("AUTH_SESSION_IDLE_SECONDS", "1800"))
AUTH_SESSION_ACTIVITY_CHECKPOINT_SECONDS = int(
    os.getenv("AUTH_SESSION_ACTIVITY_CHECKPOINT_SECONDS", "60")
)
USER_ACTIVITY_CHECKPOINT_SECONDS = int(os.getenv("USER_ACTIVITY_CHECKPOINT_SECONDS", "300"))
CSRF_USE_SESSIONS = True
AUTH_MODE = os.getenv("AUTH_MODE", "LOCAL_ONLY")
AUTH_RECOVERY_MODE = os.getenv("AUTH_RECOVERY_MODE", "ADMIN_ONLY")
AUTH_PUBLIC_BASE_URL = os.getenv("AUTH_PUBLIC_BASE_URL", "http://localhost:8080")
AUTH_RESET_ACCOUNT_LIMIT = int(os.getenv("AUTH_RESET_ACCOUNT_LIMIT", "3"))
AUTH_RESET_IP_LIMIT = int(os.getenv("AUTH_RESET_IP_LIMIT", "10"))
AUTH_RESET_WINDOW_SECONDS = int(os.getenv("AUTH_RESET_WINDOW_SECONDS", "900"))
STAGE6_DEMO_PASSWORD = os.getenv("STAGE6_DEMO_PASSWORD", "")
ALLOW_BOOTSTRAP_LOCAL_ADMIN = environment_bool("ALLOW_BOOTSTRAP_LOCAL_ADMIN", True)
DATA_UPLOAD_MAX_MEMORY_SIZE = 128 * 1024
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))
MEDIA_URL = "/_protected_media/"
MEDIA_MAX_UPLOAD_BYTES = int(os.getenv("MEDIA_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
OPS_MONITORING_TOKEN = os.getenv("OPS_MONITORING_TOKEN", "")
OPS_REALTIME_OUTBOX_RETENTION_DAYS = int(os.getenv("OPS_REALTIME_OUTBOX_RETENTION_DAYS", "7"))
OPS_NOTIFICATION_OUTBOX_RETENTION_DAYS = int(
    os.getenv("OPS_NOTIFICATION_OUTBOX_RETENTION_DAYS", "7")
)
OPS_NOTIFICATION_DELIVERY_RETENTION_DAYS = int(
    os.getenv("OPS_NOTIFICATION_DELIVERY_RETENTION_DAYS", "14")
)
OPS_DISABLED_PUSH_RETENTION_DAYS = int(os.getenv("OPS_DISABLED_PUSH_RETENTION_DAYS", "30"))
TEMPORARY_UPLOAD_RETENTION_HOURS = int(os.getenv("TEMPORARY_UPLOAD_RETENTION_HOURS", "24"))
TEMPORARY_UPLOAD_LIMIT_PER_USER = int(os.getenv("TEMPORARY_UPLOAD_LIMIT_PER_USER", "10"))

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/2")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60
CELERY_BEAT_SCHEDULE = {
    "reconcile-publications": {
        "task": "publications.reconcile",
        "schedule": 15.0,
    },
    "dispatch-realtime-outbox": {
        "task": "realtime.dispatch-outbox",
        "schedule": 2.0,
    },
    "dispatch-notification-fanout": {
        "task": "apps.notifications.tasks.dispatch_notification_fanout",
        "schedule": 2.0,
    },
    "dispatch-notification-deliveries": {
        "task": "apps.notifications.tasks.dispatch_notification_deliveries",
        "schedule": 5.0,
    },
    "cleanup-operational-data": {
        "task": "ops.cleanup-operational-data",
        "schedule": 86_400.0,
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "comment_create": "20/min",
        "comment_edit": "30/min",
        "attachment_upload": "10/min",
        "reaction": "60/min",
        "realtime_ticket": "30/min",
        "messenger_message": "120/min",
        "messenger_direct": "20/hour",
        "messenger_group": "10/hour",
        "messenger_mention_all": "10/hour",
        "messenger_people": "60/min",
        "push_subscription": "20/hour",
    },
}

REALTIME_REDIS_URL = os.getenv("REALTIME_REDIS_URL", "redis://localhost:6379/1")
REALTIME_TICKET_TTL_SECONDS = 30
REALTIME_SOCKET_LIFETIME_SECONDS: int = 900
REALTIME_MAX_SOCKETS_PER_USER = int(os.getenv("REALTIME_MAX_SOCKETS_PER_USER", "5"))
REALTIME_MAX_CLIENT_FRAMES_PER_SECOND = int(
    os.getenv("REALTIME_MAX_CLIENT_FRAMES_PER_SECOND", "30")
)

WEB_PUSH_ENABLED = environment_bool("WEB_PUSH_ENABLED", False)
WEB_PUSH_ALLOWED_HOST_SUFFIXES = tuple(
    value.strip().casefold()
    for value in os.getenv(
        "WEB_PUSH_ALLOWED_HOST_SUFFIXES",
        "fcm.googleapis.com,updates.push.services.mozilla.com,notify.windows.com,web.push.apple.com",
    ).split(",")
    if value.strip()
)
WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER = int(os.getenv("WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER", "5"))
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:security@example.invalid")
NOTIFICATION_EMAIL_ENABLED = environment_bool("NOTIFICATION_EMAIL_ENABLED", False)
NOTIFICATION_EMAIL_INACTIVE_AFTER_HOURS = int(
    os.getenv("NOTIFICATION_EMAIL_INACTIVE_AFTER_HOURS", "24")
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "tandem@example.invalid")
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = environment_bool("EMAIL_USE_TLS", False)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
REALTIME_SOCKET_LEASE_SECONDS: int = REALTIME_SOCKET_LIFETIME_SECONDS + 30
REALTIME_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "REALTIME_ALLOWED_ORIGINS", "http://localhost,http://127.0.0.1:8080"
    ).split(",")
    if origin.strip()
]
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                {
                    "address": REALTIME_REDIS_URL,
                    "socket_connect_timeout": 1,
                }
            ],
            "capacity": 100,
            "expiry": 60,
        },
    }
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Tandem Portal API",
    "VERSION": APP_VERSION,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "SERVE_AUTHENTICATION": ["rest_framework.authentication.SessionAuthentication"],
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}
API_DOCS_ENABLED = environment_bool("API_DOCS_ENABLED", False)

PORTAL_ADAPTER: str = "unavailable"
ALLOW_MOCK_PORTAL_ADAPTER: bool = False
MOCK_PORTAL_USER_ID = os.getenv("MOCK_PORTAL_USER_ID", "employee-1")
