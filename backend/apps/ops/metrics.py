import time
from collections import Counter, defaultdict
from threading import Lock

from django.db import DatabaseError, connection
from django.http import JsonResponse

HTTP_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
HTTP_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})
BACKUP_WRITE_LOCK_ID = 82_425_010

_lock = Lock()
_requests: Counter[tuple[str, str, str]] = Counter()
_duration_buckets: Counter[tuple[str, str, float]] = Counter()
_duration_count: Counter[tuple[str, str]] = Counter()
_duration_sum: defaultdict[tuple[str, str], float] = defaultdict(float)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def record_http_request(method: str, route: str, status: int, duration: float) -> None:
    method = method.upper()
    if method not in HTTP_METHODS:
        method = "OTHER"
    labels = (method, route)
    with _lock:
        _requests[method, route, str(status)] += 1
        _duration_count[labels] += 1
        _duration_sum[labels] += duration
        for bucket in HTTP_BUCKETS:
            if duration <= bucket:
                _duration_buckets[method, route, bucket] += 1


def render_http_metrics() -> list[str]:
    with _lock:
        requests = dict(_requests)
        buckets = dict(_duration_buckets)
        counts = dict(_duration_count)
        sums = dict(_duration_sum)

    lines = [
        "# HELP tandem_http_requests_total HTTP requests handled by Django.",
        "# TYPE tandem_http_requests_total counter",
    ]
    for (method, route, status), value in sorted(requests.items()):
        lines.append(
            "tandem_http_requests_total"
            f'{{method="{_escape(method)}",route="{_escape(route)}",'
            f'status="{_escape(status)}"}} {value}'
        )
    lines.extend(
        [
            "# HELP tandem_http_request_duration_seconds Django request latency.",
            "# TYPE tandem_http_request_duration_seconds histogram",
        ]
    )
    for method, route in sorted(counts):
        label_prefix = f'method="{_escape(method)}",route="{_escape(route)}"'
        for bucket in HTTP_BUCKETS:
            value = buckets.get((method, route, bucket), 0)
            lines.append(
                "tandem_http_request_duration_seconds_bucket"
                f'{{{label_prefix},le="{bucket:g}"}} {value}'
            )
        lines.append(
            "tandem_http_request_duration_seconds_bucket"
            f'{{{label_prefix},le="+Inf"}} {counts[method, route]}'
        )
        lines.append(
            f"tandem_http_request_duration_seconds_sum{{{label_prefix}}} {sums[method, route]:.9f}"
        )
        lines.append(
            f"tandem_http_request_duration_seconds_count{{{label_prefix}}} {counts[method, route]}"
        )
    return lines


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
