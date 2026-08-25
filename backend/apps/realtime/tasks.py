from celery import shared_task

from .outbox import dispatch_pending_outbox


@shared_task(name="realtime.dispatch-outbox")
def dispatch_realtime_outbox_task() -> int:
    return dispatch_pending_outbox()
