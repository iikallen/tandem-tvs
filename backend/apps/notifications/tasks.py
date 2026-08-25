from celery import shared_task

from .delivery import dispatch_pending_deliveries
from .services import dispatch_pending_fanout


@shared_task
def dispatch_notification_fanout() -> int:
    return dispatch_pending_fanout()


@shared_task
def dispatch_notification_deliveries() -> int:
    return dispatch_pending_deliveries()
