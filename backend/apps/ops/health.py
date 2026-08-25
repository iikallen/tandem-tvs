import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection

from apps.publications.tasks import RECONCILIATION_HEARTBEAT_KEY


def database_available() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception:
        return False


def media_available() -> bool:
    try:
        root = Path(settings.MEDIA_ROOT)
        if not root.is_dir():
            return False
        with tempfile.NamedTemporaryFile(dir=root, prefix=".health-", delete=True):
            pass
        return True
    except OSError:
        return False


def cache_available() -> bool:
    try:
        cache.set("tandem:ops:health", "ok", timeout=5)
        return cache.get("tandem:ops:health") == "ok"
    except Exception:
        return False


def celery_heartbeat_age() -> float | None:
    try:
        heartbeat = cache.get(RECONCILIATION_HEARTBEAT_KEY)
        return max(0.0, time.time() - float(heartbeat)) if heartbeat else None
    except (TypeError, ValueError, OSError):
        return None


def dependency_status() -> dict[str, str]:
    database = database_available()
    media = media_available()
    redis = cache_available()
    heartbeat_age = celery_heartbeat_age() if redis else None
    celery = "ok" if heartbeat_age is not None and heartbeat_age < 60 else "degraded"
    return {
        "postgres": "ok" if database else "down",
        "media": "ok" if media else "down",
        "redis": "ok" if redis else "down",
        "celery": celery,
    }
