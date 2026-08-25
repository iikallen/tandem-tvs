import json
import os
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection

from apps.publications.tasks import RECONCILIATION_HEARTBEAT_KEY

MEDIA_INTEGRITY_STATE_FILE = ".tandem-media-integrity.json"


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


def record_media_integrity_result(failures: int) -> None:
    root = Path(settings.MEDIA_ROOT)
    temporary = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        dir=root,
        prefix=f"{MEDIA_INTEGRITY_STATE_FILE}.",
        delete=False,
    )
    try:
        with temporary:
            json.dump({"checked_at": time.time(), "failures": failures}, temporary)
            temporary.write("\n")
        os.replace(temporary.name, root / MEDIA_INTEGRITY_STATE_FILE)
    except Exception:
        Path(temporary.name).unlink(missing_ok=True)
        raise


def media_integrity_result() -> tuple[int, float]:
    try:
        state = json.loads(
            (Path(settings.MEDIA_ROOT) / MEDIA_INTEGRITY_STATE_FILE).read_text(encoding="ascii")
        )
        failures = int(state["failures"])
        age = max(0.0, time.time() - float(state["checked_at"]))
        if failures < 0:
            raise ValueError
        return failures, age
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return -1, -1.0


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
