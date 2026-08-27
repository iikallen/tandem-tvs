from django.db.models import Min
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.models import NotificationDelivery, NotificationFanoutEvent
from apps.realtime.models import RealtimeOutboxEvent
from apps.realtime.socket_leases import total_active_socket_count

from .health import celery_heartbeat_age, dependency_status, media_integrity_result
from .metrics import render_http_metrics
from .permissions import HasOpsToken


class InternalOpsView(APIView):
    authentication_classes = []
    permission_classes = [HasOpsToken]


class InternalHealthView(InternalOpsView):
    @extend_schema(exclude=True)
    def get(self, request):
        dependencies = dependency_status()
        status = "ok" if all(value == "ok" for value in dependencies.values()) else "degraded"
        return Response({"status": status, "dependencies": dependencies})


def _pending_stats(queryset) -> tuple[int, float]:
    aggregate = queryset.aggregate(oldest=Min("created_at"))
    oldest = aggregate["oldest"]
    age = max(0.0, (timezone.now() - oldest).total_seconds()) if oldest else 0.0
    return queryset.count(), age


def _dependency_metrics() -> list[str]:
    dependencies = dependency_status()
    integrity_failures, integrity_age = media_integrity_result()
    return [
        "# TYPE tandem_postgres_up gauge",
        f"tandem_postgres_up {int(dependencies['postgres'] == 'ok')}",
        "# TYPE tandem_redis_up gauge",
        f"tandem_redis_up {int(dependencies['redis'] == 'ok')}",
        "# TYPE tandem_media_up gauge",
        f"tandem_media_up {int(dependencies['media'] == 'ok')}",
        "# TYPE tandem_media_integrity_failures gauge",
        f"tandem_media_integrity_failures {integrity_failures}",
        "# TYPE tandem_media_integrity_last_check_age_seconds gauge",
        f"tandem_media_integrity_last_check_age_seconds {integrity_age:.3f}",
    ]


def _operational_metrics() -> list[str]:
    realtime_count, realtime_age = _pending_stats(
        RealtimeOutboxEvent.objects.filter(delivered_at__isnull=True)
    )
    fanout_count, fanout_age = _pending_stats(
        NotificationFanoutEvent.objects.filter(processed_at__isnull=True)
    )
    delivery_count = NotificationDelivery.objects.filter(
        status=NotificationDelivery.Status.PENDING
    ).count()
    heartbeat_age = celery_heartbeat_age()
    heartbeat_metric = heartbeat_age if heartbeat_age is not None else -1
    try:
        sockets = total_active_socket_count()
    except Exception:
        sockets = 0
    return [
        "# TYPE tandem_active_realtime_sockets gauge",
        f"tandem_active_realtime_sockets {sockets}",
        "# TYPE tandem_realtime_outbox_pending gauge",
        f"tandem_realtime_outbox_pending {realtime_count}",
        "# TYPE tandem_realtime_outbox_oldest_seconds gauge",
        f"tandem_realtime_outbox_oldest_seconds {realtime_age:.3f}",
        "# TYPE tandem_notification_fanout_pending gauge",
        f"tandem_notification_fanout_pending {fanout_count}",
        "# TYPE tandem_notification_fanout_oldest_seconds gauge",
        f"tandem_notification_fanout_oldest_seconds {fanout_age:.3f}",
        "# TYPE tandem_notification_delivery_pending gauge",
        f"tandem_notification_delivery_pending {delivery_count}",
        "# TYPE tandem_celery_heartbeat_age_seconds gauge",
        f"tandem_celery_heartbeat_age_seconds {heartbeat_metric:.3f}",
    ]


class MetricsView(InternalOpsView):
    @extend_schema(exclude=True)
    def get(self, request):
        lines = [*render_http_metrics(), *_dependency_metrics()]
        try:
            lines.extend(_operational_metrics())
            collection_error = 0
        except Exception:
            collection_error = 1
        lines.extend(
            [
                "# TYPE tandem_metrics_collection_error gauge",
                f"tandem_metrics_collection_error {collection_error}",
            ]
        )
        return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; version=0.0.4")
