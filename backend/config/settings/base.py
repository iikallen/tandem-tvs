import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY: str = "development-only-not-for-production"
DEBUG: bool = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "apps.core",
    "apps.identity",
    "apps.organization",
    "apps.publications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
    }
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
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }

LANGUAGE_CODE = "ru"
TIME_ZONE = "Asia/Qyzylorda"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "identity.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.identity.authentication.PortalAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Tandem Portal API",
    "VERSION": "1.0.0",
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "SERVE_AUTHENTICATION": ["apps.identity.authentication.PortalAuthentication"],
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}
API_DOCS_ENABLED: bool = False

PORTAL_ADAPTER: str = ""
ALLOW_MOCK_PORTAL_ADAPTER: bool = False
MOCK_PORTAL_USER_ID = os.getenv("MOCK_PORTAL_USER_ID", "employee-1")
