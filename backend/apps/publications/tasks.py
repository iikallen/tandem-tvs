import time

from celery import shared_task
from django.core.cache import cache

from .services import reconcile_publications

RECONCILIATION_HEARTBEAT_KEY = "tandem:celery:reconcile-heartbeat"
RECONCILIATION_HEARTBEAT_TTL_SECONDS = 60


@shared_task(name="publications.reconcile")
def reconcile_publications_task() -> dict[str, int]:
    result = reconcile_publications()
    cache.set(
        RECONCILIATION_HEARTBEAT_KEY,
        time.time(),
        timeout=RECONCILIATION_HEARTBEAT_TTL_SECONDS,
    )
    return result
