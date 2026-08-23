from celery import shared_task

from .services import reconcile_publications


@shared_task(name="publications.reconcile")
def reconcile_publications_task() -> dict[str, int]:
    return reconcile_publications()
