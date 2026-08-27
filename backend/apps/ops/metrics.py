import os
import time

from django.db import DatabaseError, connection
from django.http import JsonResponse
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, multiprocess

HTTP_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
HTTP_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})
BACKUP_WRITE_LOCK_ID = 82_425_010

METRICS_REGISTRY = CollectorRegistry()
HTTP_REQUESTS = Counter(
    "tandem_http_requests_total",
    "HTTP requests handled by Django.",
    ("method", "route", "status"),
    registry=METRICS_REGISTRY,
)
HTTP_DURATION = Histogram(
    "tandem_http_request_duration_seconds",
    "Django request latency.",
    ("method", "route"),
    buckets=HTTP_BUCKETS,
    registry=METRICS_REGISTRY,
)


def record_http_request(method: str, route: str, status: int, duration: float) -> None:
    method = method.upper()
    if method not in HTTP_METHODS:
        method = "OTHER"
    try:
        HTTP_REQUESTS.labels(method=method, route=route, status=str(status)).inc()
        HTTP_DURATION.labels(method=method, route=route).observe(duration)
    except Exception:
        # Monitoring must fail open when its local multiprocess files are unavailable.
        return


def render_http_metrics() -> list[str]:
    registry = METRICS_REGISTRY
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    return generate_latest(registry).decode("utf-8").rstrip().splitlines()


class MetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        status = 500
        backup_lock = False
        try:
            if (
                request.method not in {"GET", "HEAD", "OPTIONS"}
                and connection.vendor == "postgresql"
            ):
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_try_advisory_lock_shared(%s)", [BACKUP_WRITE_LOCK_ID]
                        )
                        backup_lock = bool(cursor.fetchone()[0])
                except DatabaseError:
                    response = JsonResponse(
                        {"detail": "Writes are temporarily unavailable."}, status=503
                    )
                    status = response.status_code
                    return response
                if not backup_lock:
                    response = JsonResponse(
                        {"detail": "Backup in progress; retry the write shortly."}, status=503
                    )
                    response["Retry-After"] = "60"
                    status = response.status_code
                    return response
            response = self.get_response(request)
            status = response.status_code
            return response
        finally:
            if backup_lock:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_unlock_shared(%s)", [BACKUP_WRITE_LOCK_ID]
                        )
                except DatabaseError:
                    connection.close()
            match = getattr(request, "resolver_match", None)
            route = match.view_name if match and match.view_name else "unmatched"
            record_http_request(request.method, route, status, time.perf_counter() - started)
