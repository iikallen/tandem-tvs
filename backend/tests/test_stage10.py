import hashlib
import io
import json
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.sessions.models import Session
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponse
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.models import AccessGrant, User
from apps.messenger.models import Message
from apps.messenger.serializers import MessageSerializer
from apps.messenger.services import create_direct_conversation, send_message
from apps.notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationFanoutEvent,
    PushSubscription,
)
from apps.notifications.services import dispatch_pending_fanout
from apps.ops import tasks as ops_tasks
from apps.ops.management.commands.seed_load_profile import (
    Command as SeedLoadProfileCommand,
)
from apps.ops.management.commands.seed_load_profile import (
    safe_load_environment,
)
from apps.ops.metrics import MetricsMiddleware, record_http_request, render_http_metrics
from apps.ops.tasks import cleanup_operational_data
from apps.publications.models import AudienceRule, AuditEvent, Category, MediaAsset, Publication
from apps.realtime.models import RealtimeOutboxEvent

OPS_TOKEN = "stage10-test-monitoring-token-32-chars"


def dependencies(**overrides: str) -> dict[str, str]:
    result = {"postgres": "ok", "media": "ok", "redis": "ok", "celery": "ok"}
    result.update(overrides)
    return result


def test_load_seed_requires_both_purpose_and_isolated_database_name():
    assert safe_load_environment("stage10-load", "stage10_load_release")
    assert not safe_load_environment("stage10-load", "tandem")
    assert not safe_load_environment("production", "stage10_load_release")


@pytest.mark.django_db
def test_load_seed_rerun_never_rewinds_live_conversation_sequence():
    first = User.objects.create(username="load-seed-first", full_name="First")
    second = User.objects.create(username="load-seed-second", full_name="Second")
    conversation, _ = create_direct_conversation(first, second)
    command = SeedLoadProfileCommand()
    seeded = command._messages(2, [conversation], [first, second], timezone.now())
    assert len(seeded) == 2
    live, created = send_message(
        conversation,
        author=first,
        client_message_id=uuid.uuid4(),
        body="Committed after the seed",
    )
    assert created and live.sequence == 3

    conversation.refresh_from_db()
    command._messages(2, [conversation], [first, second], timezone.now() - timedelta(days=1))
    conversation.refresh_from_db()
    assert conversation.last_sequence == 3
    assert Message.objects.filter(conversation=conversation, sequence=3, pk=live.pk).exists()


@pytest.mark.django_db
def test_notification_fanout_default_batch_finishes_in_bounded_slices():
    NotificationFanoutEvent.objects.bulk_create(
        [
            NotificationFanoutEvent(
                event_key=f"stage10-batch-{index}",
                event_type=Notification.Type.COMMENT_REPLY,
                source_id=uuid.uuid4(),
                payload={"recipient_ids": []},
            )
            for index in range(26)
        ]
    )

    assert dispatch_pending_fanout() == 10
    assert NotificationFanoutEvent.objects.filter(processed_at__isnull=False).count() == 10
    assert NotificationFanoutEvent.objects.filter(processed_at__isnull=True).count() == 16


@pytest.mark.django_db
@override_settings(OPS_MONITORING_TOKEN=OPS_TOKEN)
def test_internal_ops_endpoints_require_exact_bearer_token(monkeypatch):
    monkeypatch.setattr("apps.ops.views.dependency_status", dependencies)
    monkeypatch.setattr("apps.ops.views._operational_metrics", lambda: ["tandem_test 1"])
    client = APIClient()

    assert client.get("/internal/health").status_code == 403
    assert client.get("/internal/metrics", HTTP_AUTHORIZATION="Bearer wrong").status_code == 403

    health = client.get("/internal/health", HTTP_AUTHORIZATION=f"Bearer {OPS_TOKEN}")
    metrics = client.get("/internal/metrics", HTTP_AUTHORIZATION=f"Bearer {OPS_TOKEN}")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "dependencies": dependencies()}
    assert metrics.status_code == 200
    assert metrics["Content-Type"] == "text/plain; version=0.0.4"
    assert b"tandem_test 1" in metrics.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("dependency_overrides", "expected_status", "expected_body_status"),
    [
        ({"redis": "down"}, 200, "degraded"),
        ({"celery": "degraded"}, 200, "degraded"),
        ({"postgres": "down"}, 503, "unavailable"),
        ({"media": "down"}, 503, "unavailable"),
    ],
)
def test_public_readiness_distinguishes_required_and_degraded_dependencies(
    monkeypatch, dependency_overrides, expected_status, expected_body_status
):
    state = dependencies(**dependency_overrides)
    monkeypatch.setattr("apps.core.views.dependency_status", lambda: state)

    response = APIClient().get("/api/v1/health/ready")

    assert response.status_code == expected_status
    assert response.json() == {"status": expected_body_status}


@pytest.mark.django_db
def test_operational_metrics_include_backlogs_dependencies_and_http_latency(monkeypatch):
    from apps.ops import views

    monkeypatch.setattr(views, "dependency_status", dependencies)
    monkeypatch.setattr(views, "media_integrity_result", lambda: (0, 1.5))
    monkeypatch.setattr(views, "celery_heartbeat_age", lambda: 12.5)
    monkeypatch.setattr(views, "total_active_socket_count", lambda: 3)
    APIClient().get("/api/v1/health/live")

    rendered = "\n".join(
        [*views.render_http_metrics(), *views._dependency_metrics(), *views._operational_metrics()]
    )

    assert 'route="health-live"' in rendered
    assert "tandem_http_request_duration_seconds_bucket" in rendered
    assert "tandem_postgres_up 1" in rendered
    assert "tandem_redis_up 1" in rendered
    assert "tandem_active_realtime_sockets 3" in rendered
    assert "tandem_realtime_outbox_pending 0" in rendered
    assert "tandem_notification_fanout_pending 0" in rendered
    assert "tandem_notification_delivery_pending 0" in rendered
    assert "tandem_celery_heartbeat_age_seconds 12.500" in rendered
    assert "tandem_media_integrity_last_check_age_seconds 1.500" in rendered


def test_http_method_metric_label_has_a_finite_fallback():
    record_http_request("BREW", 'method-cardinality-test\\\n"', 418, 0.01)

    rendered = "\n".join(render_http_metrics())

    assert 'method="OTHER",route="method-cardinality-test\\\\\\n\\""' in rendered
    assert 'method="BREW"' not in rendered


def test_nginx_access_log_and_prometheus_rules_preserve_observability_privacy():
    repository_root = Path(__file__).resolve().parents[2]
    nginx = (repository_root / "frontend/infra/nginx.conf").read_text()
    alerts = (repository_root / "ops/prometheus/alerts.yml").read_text()

    log_format = nginx.split("geo $tandem_trusted_tunnel_peer", 1)[0]
    assert "$request_uri" not in log_format
    assert "$uri" not in log_format
    assert "method=$request_method status=$status" in log_format
    protected_media = nginx.split("location /_protected_media/", 1)[1].split("location /ws/", 1)[0]
    assert "X-Frame-Options DENY" in protected_media
    assert "Content-Security-Policy" in protected_media
    assert "Content-Security-Policy-Report-Only" not in protected_media
    assert "clamp_min" not in alerts
    assert "absent(tandem_postgres_up)" in alerts


def test_realtime_acceptance_scripts_can_target_the_production_origin():
    scripts = Path(__file__).resolve().parents[1] / "scripts"

    for stage in (7, 8, 9):
        verifier = (scripts / f"verify_stage{stage}.py").read_text()
        assert 'os.getenv("ACCEPTANCE_ORIGIN", "http://localhost")' in verifier
        assert "origin=ACCEPTANCE_ORIGIN" in verifier


def test_mutating_http_requests_coordinate_with_backup_write_lock(monkeypatch):
    from apps.ops import metrics

    queries = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, params):
            queries.append((query, params))

        def fetchone(self):
            return (True,)

    fake_connection = SimpleNamespace(vendor="postgresql", cursor=lambda: Cursor())
    monkeypatch.setattr(metrics, "connection", fake_connection)
    request = SimpleNamespace(method="POST", resolver_match=None)

    response = MetricsMiddleware(lambda _request: HttpResponse(status=204))(request)

    assert response.status_code == 204
    assert "pg_try_advisory_lock_shared" in queries[0][0]
    assert "pg_advisory_unlock_shared" in queries[1][0]


def test_mutating_requests_fail_closed_during_backup_or_database_error(monkeypatch):
    from apps.ops import metrics

    class Cursor:
        def __init__(self, granted):
            self.granted = granted

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, _query, _params):
            return None

        def fetchone(self):
            return (self.granted,)

    request = SimpleNamespace(method="POST", resolver_match=None)
    monkeypatch.setattr(
        metrics,
        "connection",
        SimpleNamespace(vendor="postgresql", cursor=lambda: Cursor(False)),
    )
    blocked = MetricsMiddleware(lambda _request: HttpResponse(status=204))(request)
    assert blocked.status_code == 503
    assert blocked["Retry-After"] == "60"

    def unavailable_cursor():
        raise metrics.DatabaseError("unavailable")

    monkeypatch.setattr(
        metrics,
        "connection",
        SimpleNamespace(vendor="postgresql", cursor=unavailable_cursor),
    )
    unavailable = MetricsMiddleware(lambda _request: HttpResponse(status=204))(request)
    assert unavailable.status_code == 503
    assert "temporarily unavailable" in unavailable.content.decode()


def test_backup_lock_unlock_failure_discards_database_connection(monkeypatch):
    from apps.ops import metrics

    calls = 0
    closed = False

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, _query, _params):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise metrics.DatabaseError("unlock failed")

        def fetchone(self):
            return (True,)

    def close():
        nonlocal closed
        closed = True

    monkeypatch.setattr(
        metrics,
        "connection",
        SimpleNamespace(vendor="postgresql", cursor=lambda: Cursor(), close=close),
    )
    request = SimpleNamespace(method="PATCH", resolver_match=None)
    response = MetricsMiddleware(lambda _request: HttpResponse(status=204))(request)

    assert response.status_code == 204
    assert closed


def test_health_probe_error_paths_and_durable_media_state(tmp_path, monkeypatch):
    from apps.ops import health

    monkeypatch.setattr(
        health,
        "connection",
        SimpleNamespace(cursor=lambda: (_ for _ in ()).throw(RuntimeError())),
    )
    assert not health.database_available()

    with override_settings(MEDIA_ROOT=tmp_path / "missing"):
        assert not health.media_available()

    monkeypatch.setattr(
        health,
        "cache",
        SimpleNamespace(set=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError())),
    )
    assert not health.cache_available()
    monkeypatch.setattr(
        health,
        "cache",
        SimpleNamespace(get=lambda _key: "not-a-timestamp"),
    )
    assert health.celery_heartbeat_age() is None

    with override_settings(MEDIA_ROOT=tmp_path):
        health.record_media_integrity_result(2)
        failures, age = health.media_integrity_result()
        assert failures == 2
        assert age >= 0
        (tmp_path / health.MEDIA_INTEGRITY_STATE_FILE).write_text(
            json.dumps({"failures": -1, "checked_at": 0}), encoding="ascii"
        )
        assert health.media_integrity_result() == (-1, -1.0)


def test_media_integrity_state_write_is_atomic_on_replace_failure(tmp_path, monkeypatch):
    from apps.ops import health

    def fail_replace(*_args):
        raise OSError("replace failed")

    monkeypatch.setattr(health.os, "replace", fail_replace)
    with override_settings(MEDIA_ROOT=tmp_path), pytest.raises(OSError, match="replace failed"):
        health.record_media_integrity_result(0)

    assert list(tmp_path.iterdir()) == []


def test_dependency_status_reports_each_unavailable_component(monkeypatch):
    from apps.ops import health

    monkeypatch.setattr(health, "database_available", lambda: False)
    monkeypatch.setattr(health, "media_available", lambda: False)
    monkeypatch.setattr(health, "cache_available", lambda: False)

    assert health.dependency_status() == {
        "postgres": "down",
        "media": "down",
        "redis": "down",
        "celery": "degraded",
    }


@pytest.mark.django_db
@override_settings(OPS_MONITORING_TOKEN=OPS_TOKEN)
def test_operational_metrics_fail_closed_per_dependency_and_as_a_whole(monkeypatch):
    from apps.ops import views

    monkeypatch.setattr(views, "dependency_status", dependencies)
    monkeypatch.setattr(views, "media_integrity_result", lambda: (2, 3.5))
    monkeypatch.setattr(views, "celery_heartbeat_age", lambda: None)
    monkeypatch.setattr(
        views,
        "total_active_socket_count",
        lambda: (_ for _ in ()).throw(RuntimeError()),
    )
    rendered = "\n".join(views._operational_metrics())
    assert "tandem_active_realtime_sockets 0" in rendered
    assert "tandem_celery_heartbeat_age_seconds -1.000" in rendered

    monkeypatch.setattr(
        views, "_operational_metrics", lambda: (_ for _ in ()).throw(RuntimeError())
    )
    response = APIClient().get(
        "/internal/metrics",
        HTTP_AUTHORIZATION=f"Bearer {OPS_TOKEN}",
    )
    assert response.status_code == 200
    assert b"tandem_postgres_up 1" in response.content
    assert b"tandem_redis_up 1" in response.content
    assert b"tandem_media_up 1" in response.content
    assert b"tandem_media_integrity_failures 2" in response.content
    assert b"tandem_metrics_collection_error 1" in response.content


@pytest.mark.django_db
def test_message_resource_preview_is_local_visible_news_only():
    sender = User.objects.create(username="preview-sender", full_name="Preview Sender")
    recipient = User.objects.create(username="preview-recipient", full_name="Preview Recipient")
    for user in (sender, recipient):
        AccessGrant.objects.create(
            user=user,
            module=AccessGrant.Module.MESSENGER,
            role=AccessGrant.Role.MEMBER,
        )
    conversation, _ = create_direct_conversation(sender, recipient)
    category = Category.objects.create(slug="preview", name="Preview")
    publication = Publication.objects.create(
        title="Visible publication",
        slug="visible-publication",
        summary="Visible publication",
        category=category,
        author=sender,
        status=Publication.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    AudienceRule.objects.create(publication=publication, kind=AudienceRule.Kind.ALL)
    visible, _ = send_message(
        conversation,
        author=sender,
        client_message_id=uuid.uuid4(),
        body="Read /news/visible-publication",
    )
    external, _ = send_message(
        conversation,
        author=sender,
        client_message_id=uuid.uuid4(),
        body="Ignore https://evil.example/news/visible-publication",
    )
    request = APIClient().get("/api/v1/health/live").wsgi_request
    request.user = recipient

    preview = MessageSerializer(visible, context={"request": request}).data["resource_preview"]
    assert preview == {
        "type": "publication",
        "id": str(publication.pk),
        "title": publication.title,
        "url": f"/news/{publication.pk}",
    }
    assert (
        MessageSerializer(external, context={"request": request}).data["resource_preview"] is None
    )
    assert MessageSerializer(visible).data["resource_preview"] is None


@pytest.mark.django_db
def test_media_integrity_verifies_hash_and_reports_orphans(tmp_path):
    payload = b"stage-10-media"
    media_path = tmp_path / "publications" / "asset.bin"
    media_path.parent.mkdir()
    media_path.write_bytes(payload)
    uploader = User.objects.create(username="integrity", full_name="Integrity User")
    MediaAsset.objects.create(
        original_name="asset.bin",
        storage_key="publications/asset.bin",
        file="publications/asset.bin",
        mime_type="application/octet-stream",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=uploader,
    )
    pending_path = tmp_path / "publications" / "pending.bin"
    pending_path.write_bytes(b"pending")
    MediaAsset.objects.create(
        original_name="pending.bin",
        storage_key="publications/pending.bin",
        file="publications/pending.bin",
        mime_type="application/octet-stream",
        size=7,
        sha256="0" * 64,
        kind=MediaAsset.Kind.DOCUMENT,
        status=MediaAsset.Status.PENDING_SCAN,
        uploader=uploader,
    )

    stdout = io.StringIO()
    with override_settings(MEDIA_ROOT=tmp_path):
        call_command("verify_media_integrity", stdout=stdout)
        (tmp_path / "orphan.bin").write_bytes(b"orphan")
        stderr = io.StringIO()
        with pytest.raises(CommandError, match="1 media integrity failures"):
            call_command("verify_media_integrity", stderr=stderr)

    assert "Media integrity: PASS" in stdout.getvalue()
    assert "Orphan media file: orphan.bin" in stderr.getvalue()
    state = json.loads((tmp_path / ".tandem-media-integrity.json").read_text())
    assert state["failures"] == 1
    assert state["checked_at"] > 0


@pytest.mark.django_db
@override_settings(
    OPS_REALTIME_OUTBOX_RETENTION_DAYS=1,
    OPS_NOTIFICATION_OUTBOX_RETENTION_DAYS=1,
    OPS_NOTIFICATION_DELIVERY_RETENTION_DAYS=1,
    OPS_DISABLED_PUSH_RETENTION_DAYS=1,
)
def test_cleanup_deletes_only_expired_operational_rows(monkeypatch):
    now = timezone.now()
    old = now - timedelta(days=2)
    user = User.objects.create(username="cleanup", full_name="Cleanup User")
    notification = Notification.objects.create(
        recipient=user,
        notification_type=Notification.Type.NEW_MESSAGE,
        source_type="MESSAGE",
        source_id=uuid.uuid4(),
        dedupe_key="cleanup-notification",
    )

    expired_session = Session.objects.create(
        session_key="expired-session", session_data="", expire_date=old
    )
    live_session = Session.objects.create(
        session_key="live-session", session_data="", expire_date=now + timedelta(days=1)
    )
    delivered = RealtimeOutboxEvent.objects.create(
        group_name="user-1", event_type="test", payload={}, delivered_at=old
    )
    pending = RealtimeOutboxEvent.objects.create(group_name="user-1", event_type="test", payload={})
    processed = NotificationFanoutEvent.objects.create(
        event_key="processed",
        event_type=Notification.Type.NEW_MESSAGE,
        source_id=uuid.uuid4(),
        processed_at=old,
    )
    pending_fanout = NotificationFanoutEvent.objects.create(
        event_key="pending",
        event_type=Notification.Type.NEW_MESSAGE,
        source_id=uuid.uuid4(),
    )
    sent = NotificationDelivery.objects.create(
        notification=notification,
        channel=NotificationDelivery.Channel.PUSH,
        event_version=1,
        status=NotificationDelivery.Status.SENT,
    )
    pending_delivery = NotificationDelivery.objects.create(
        notification=notification,
        channel=NotificationDelivery.Channel.EMAIL,
        event_version=1,
    )
    disabled_push = PushSubscription.objects.create(
        user=user,
        endpoint="https://push.example.test/disabled",
        p256dh="key",
        auth="auth",
        enabled=False,
    )
    enabled_push = PushSubscription.objects.create(
        user=user, endpoint="https://push.example.test/enabled", p256dh="key", auth="auth"
    )
    NotificationDelivery.objects.filter(pk=sent.pk).update(created_at=old)
    PushSubscription.objects.filter(pk__in=[disabled_push.pk, enabled_push.pk]).update(
        updated_at=old
    )

    atomic_calls = 0
    real_atomic = ops_tasks.transaction.atomic

    def counted_atomic(*args, **kwargs):
        nonlocal atomic_calls
        atomic_calls += 1
        return real_atomic(*args, **kwargs)

    monkeypatch.setattr(ops_tasks, "CLEANUP_BATCH_SIZE", 1)
    monkeypatch.setattr(ops_tasks.transaction, "atomic", counted_atomic)
    result = cleanup_operational_data()

    assert result == {
        "expired_sessions": 1,
        "realtime_outbox": 1,
        "notification_fanout": 1,
        "notification_deliveries": 1,
        "disabled_push_subscriptions": 1,
    }
    assert atomic_calls >= 5
    assert not Session.objects.filter(pk=expired_session.pk).exists()
    assert Session.objects.filter(pk=live_session.pk).exists()
    assert not RealtimeOutboxEvent.objects.filter(pk=delivered.pk).exists()
    assert RealtimeOutboxEvent.objects.filter(pk=pending.pk).exists()
    assert not NotificationFanoutEvent.objects.filter(pk=processed.pk).exists()
    assert NotificationFanoutEvent.objects.filter(pk=pending_fanout.pk).exists()
    assert not NotificationDelivery.objects.filter(pk=sent.pk).exists()
    assert NotificationDelivery.objects.filter(pk=pending_delivery.pk).exists()
    assert not PushSubscription.objects.filter(pk=disabled_push.pk).exists()
    assert PushSubscription.objects.filter(pk=enabled_push.pk).exists()
    assert User.objects.filter(pk=user.pk).exists()
    assert Notification.objects.filter(pk=notification.pk).exists()


@pytest.mark.django_db
@override_settings(APP_VERSION="1.0.0", APP_GIT_SHA="b" * 40)
def test_runtime_metadata_exposes_immutable_release_identity():
    response = APIClient().get("/api/v1/runtime/meta")

    assert response.status_code == 200
    assert response.json()["version"] == "1.0.0"
    assert response.json()["revision"] == "b" * 40


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("grants", "is_member", "expected_status"),
    [
        (((AccessGrant.Module.MESSENGER, AccessGrant.Role.MEMBER),), True, 200),
        (((AccessGrant.Module.MESSENGER, AccessGrant.Role.MEMBER),), False, 404),
        (((AccessGrant.Module.MESSENGER, AccessGrant.Role.ADMIN),), False, 404),
        (
            (
                (AccessGrant.Module.MESSENGER, AccessGrant.Role.MEMBER),
                (AccessGrant.Module.PLATFORM, AccessGrant.Role.ADMIN),
            ),
            False,
            404,
        ),
        (((AccessGrant.Module.NEWS, AccessGrant.Role.EDITOR),), False, 403),
    ],
)
def test_private_conversation_access_is_membership_scoped(grants, is_member, expected_status):
    owner = User.objects.create(username="matrix-owner", full_name="Matrix Owner")
    AccessGrant.objects.create(
        user=owner, module=AccessGrant.Module.MESSENGER, role=AccessGrant.Role.MEMBER
    )
    subject = User.objects.create(username="matrix-subject", full_name="Matrix Subject")
    for module, role in grants:
        AccessGrant.objects.create(user=subject, module=module, role=role)
    peer = subject
    if not is_member:
        peer = User.objects.create(username="matrix-peer", full_name="Matrix Peer")
        AccessGrant.objects.create(
            user=peer, module=AccessGrant.Module.MESSENGER, role=AccessGrant.Role.MEMBER
        )
    conversation, _ = create_direct_conversation(owner, peer)
    send_message(
        conversation,
        author=owner,
        client_message_id=uuid.uuid4(),
        body="private message",
    )
    client = APIClient()
    client.force_authenticate(subject)

    detail = client.get(f"/api/v1/messenger/conversations/{conversation.pk}")
    messages = client.get(f"/api/v1/messenger/conversations/{conversation.pk}/messages")

    assert detail.status_code == expected_status
    assert messages.status_code == expected_status
    if expected_status == 200:
        assert messages.data["messages"][0]["body"] == "private message"
    else:
        assert b"private message" not in messages.content


@pytest.mark.django_db
def test_platform_admin_cannot_read_private_attachment_or_search():
    owner = User.objects.create(username="idor-owner", full_name="IDOR Owner")
    peer = User.objects.create(username="idor-peer", full_name="IDOR Peer")
    platform_admin = User.objects.create(username="idor-admin", full_name="IDOR Admin")
    for user in (owner, peer, platform_admin):
        AccessGrant.objects.create(
            user=user, module=AccessGrant.Module.MESSENGER, role=AccessGrant.Role.MEMBER
        )
    AccessGrant.objects.create(
        user=platform_admin,
        module=AccessGrant.Module.PLATFORM,
        role=AccessGrant.Role.ADMIN,
    )
    conversation, _ = create_direct_conversation(owner, peer)
    asset = MediaAsset.objects.create(
        original_name="private.txt",
        storage_key="messenger/private.txt",
        file="messenger/private.txt",
        mime_type="text/plain",
        size=14,
        sha256="a" * 64,
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=owner,
        is_messenger_only=True,
    )
    send_message(
        conversation,
        author=owner,
        client_message_id=uuid.uuid4(),
        body="secret attachment",
        attachment_ids=[asset.pk],
    )
    admin_client = APIClient()
    admin_client.force_authenticate(platform_admin)
    peer_client = APIClient()
    peer_client.force_authenticate(peer)

    assert peer_client.get(f"/api/v1/media/{asset.pk}/content").status_code == 200
    assert admin_client.get(f"/api/v1/media/{asset.pk}/content").status_code == 404
    search = admin_client.get(f"/api/v1/messenger/conversations/{conversation.pk}/search?q=secret")
    assert search.status_code == 404
    assert b"secret attachment" not in search.content


@pytest.mark.django_db
def test_notification_idor_is_not_found_and_does_not_mutate_owner_row():
    owner = User.objects.create(username="notification-owner", full_name="Notification Owner")
    platform_admin = User.objects.create(
        username="notification-admin", full_name="Notification Admin"
    )
    AccessGrant.objects.create(
        user=platform_admin,
        module=AccessGrant.Module.PLATFORM,
        role=AccessGrant.Role.ADMIN,
    )
    row = Notification.objects.create(
        recipient=owner,
        notification_type=Notification.Type.NEW_PUBLICATION,
        source_type="PUBLICATION",
        source_id=uuid.uuid4(),
        dedupe_key="private-notification",
    )
    client = APIClient()
    client.force_authenticate(platform_admin)

    assert client.post(f"/api/v1/notifications/{row.pk}/read").status_code == 404
    assert client.get("/api/v1/notifications").data["results"] == []
    row.refresh_from_db()
    assert row.read_at is None


@pytest.mark.django_db
def test_ops_health_probes_cover_success_failure_and_heartbeat(monkeypatch, tmp_path):
    from apps.ops import health

    assert health.database_available()
    with override_settings(MEDIA_ROOT=tmp_path):
        assert health.media_available()
    with override_settings(MEDIA_ROOT=tmp_path / "missing"):
        assert not health.media_available()
    with monkeypatch.context() as scoped, override_settings(MEDIA_ROOT=tmp_path):
        scoped.setattr(
            health.tempfile,
            "NamedTemporaryFile",
            lambda **_kwargs: (_ for _ in ()).throw(OSError("media read-only")),
        )
        assert not health.media_available()
    assert health.cache_available()

    monkeypatch.setattr(health.time, "time", lambda: 100.0)
    monkeypatch.setattr(health.cache, "get", lambda _key: "80.5")
    assert health.celery_heartbeat_age() == 19.5
    monkeypatch.setattr(health.cache, "get", lambda _key: object())
    assert health.celery_heartbeat_age() is None

    with monkeypatch.context() as scoped:
        scoped.setattr(
            health.connection,
            "cursor",
            lambda: (_ for _ in ()).throw(ConnectionError("database down")),
        )
        assert not health.database_available()
    with monkeypatch.context() as scoped:
        scoped.setattr(
            health.cache,
            "set",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("cache down")),
        )
        assert not health.cache_available()

    monkeypatch.setattr(health, "database_available", lambda: False)
    monkeypatch.setattr(health, "media_available", lambda: True)
    monkeypatch.setattr(health, "cache_available", lambda: True)
    monkeypatch.setattr(health, "celery_heartbeat_age", lambda: 61.0)
    assert health.dependency_status() == {
        "postgres": "down",
        "media": "ok",
        "redis": "ok",
        "celery": "degraded",
    }


@pytest.mark.django_db
def test_verify_restored_state_rejects_incomplete_and_accepts_core_state(tmp_path):
    with (
        override_settings(MEDIA_ROOT=tmp_path),
        pytest.raises(CommandError, match="Restored state is incomplete"),
    ):
        call_command("verify_restored_state")

    owner = User.objects.create(username="restore-owner", full_name="Restore Owner")
    peer = User.objects.create(username="restore-peer", full_name="Restore Peer")
    for user in (owner, peer):
        AccessGrant.objects.create(
            user=user, module=AccessGrant.Module.MESSENGER, role=AccessGrant.Role.MEMBER
        )
    conversation, _ = create_direct_conversation(owner, peer)
    message, _ = send_message(
        conversation,
        author=owner,
        client_message_id=uuid.uuid4(),
        body="restored message",
    )
    category = Category.objects.create(slug="restored", name="Restored")
    Publication.objects.create(
        title="Restored publication",
        slug="restored-publication",
        summary="Restored publication",
        category=category,
        author=owner,
    )
    Notification.objects.create(
        recipient=peer,
        notification_type=Notification.Type.NEW_MESSAGE,
        source_type="MESSAGE",
        source_id=message.pk,
        dedupe_key="restored-message",
    )
    payload = b"restored media"
    path = tmp_path / "restored" / "media.bin"
    path.parent.mkdir()
    path.write_bytes(payload)
    MediaAsset.objects.create(
        original_name="media.bin",
        storage_key="restored/media.bin",
        file="restored/media.bin",
        mime_type="application/octet-stream",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=owner,
    )
    stdout = io.StringIO()

    with override_settings(MEDIA_ROOT=tmp_path):
        call_command("verify_restored_state", stdout=stdout)

    assert "Restored application state: PASS" in stdout.getvalue()


@pytest.mark.django_db
def test_editorial_audit_is_news_admin_only_and_serializes_state():
    admin = User.objects.create(username="audit-admin", full_name="Audit Admin")
    editor = User.objects.create(username="audit-editor", full_name="Audit Editor")
    for user, role in (
        (admin, AccessGrant.Role.ADMIN),
        (editor, AccessGrant.Role.EDITOR),
    ):
        AccessGrant.objects.create(user=user, module=AccessGrant.Module.NEWS, role=role)
    event = AuditEvent.objects.create(
        actor=admin,
        event_type=AuditEvent.Type.UPDATED,
        target_type=AuditEvent.TargetType.PUBLICATION,
        target_id="publication-1",
        previous_state={"title": "Before"},
        new_state={"title": "After"},
    )
    client = APIClient()

    assert client.get("/api/v1/editorial/audit").status_code in {401, 403}
    client.force_authenticate(editor)
    assert client.get("/api/v1/editorial/audit").status_code == 403
    client.force_authenticate(admin)
    response = client.get("/api/v1/editorial/audit")

    assert response.status_code == 200
    assert response.data["results"][0] == {
        "id": event.pk,
        "event_type": AuditEvent.Type.UPDATED,
        "target_type": AuditEvent.TargetType.PUBLICATION,
        "target_id": "publication-1",
        "actor": {
            "id": admin.pk,
            "username": "audit-admin",
            "portal_id": None,
            "full_name": "Audit Admin",
            "job_title": "",
        },
        "previous_state": {"title": "Before"},
        "new_state": {"title": "After"},
        "created_at": response.data["results"][0]["created_at"],
    }


@pytest.mark.django_db
@override_settings(MEDIA_MAX_UPLOAD_BYTES=4096)
def test_engagement_media_and_retention_policy_validation_and_enforcement(tmp_path):
    admin = User.objects.create(username="policy-admin", full_name="Policy Admin")
    AccessGrant.objects.create(
        user=admin, module=AccessGrant.Module.NEWS, role=AccessGrant.Role.ADMIN
    )
    client = APIClient()
    client.force_authenticate(admin)
    path = "/api/v1/editorial/settings/engagement"

    configured = client.patch(
        path,
        {
            "max_comment_attachment_bytes": 1024,
            "allowed_media_extensions": [".pdf"],
            "message_retention_days": 30,
            "media_retention_days": 90,
        },
        format="json",
    )
    assert configured.status_code == 200
    assert configured.data["message_retention_days"] == 30
    assert configured.data["media_retention_days"] == 90

    with override_settings(MEDIA_ROOT=tmp_path):
        too_large = client.post(
            "/api/v1/editorial/media",
            {
                "file": SimpleUploadedFile(
                    "policy.pdf",
                    b"%PDF-1.7\n" + b"x" * 1024,
                    content_type="application/pdf",
                )
            },
            format="multipart",
        )
    assert too_large.status_code == 400
    assert not MediaAsset.objects.filter(original_name="policy.pdf").exists()

    allow_images_only = client.patch(
        path,
        {
            "max_comment_attachment_bytes": 4096,
            "allowed_media_extensions": [".png"],
        },
        format="json",
    )
    assert allow_images_only.status_code == 200
    with override_settings(MEDIA_ROOT=tmp_path):
        disallowed_type = client.post(
            "/api/v1/editorial/media",
            {
                "file": SimpleUploadedFile(
                    "disallowed.pdf",
                    b"%PDF-1.7\n",
                    content_type="application/pdf",
                )
            },
            format="multipart",
        )
    assert disallowed_type.status_code == 400
    assert not MediaAsset.objects.filter(original_name="disallowed.pdf").exists()

    invalid = client.patch(
        path,
        {
            "allowed_media_extensions": [".PDF", ".pdf"],
            "message_retention_days": 3651,
            "media_retention_days": 3651,
        },
        format="json",
    )
    assert invalid.status_code == 400
    assert set(invalid.data) == {
        "allowed_media_extensions",
        "message_retention_days",
        "media_retention_days",
    }


@pytest.mark.django_db
def test_department_analytics_summary_and_csv_export(monkeypatch):
    editor = User.objects.create(username="department-editor", full_name="Department Editor")
    AccessGrant.objects.create(
        user=editor, module=AccessGrant.Module.NEWS, role=AccessGrant.Role.EDITOR
    )
    rows = [
        {
            "publication_id": "publication-1",
            "title": "Policy",
            "category": "Company",
            "recipients": 4,
            "views": 3,
            "unique_views": 3,
            "reach_percent": "75.0",
            "comments": 1,
            "reactions": 1,
            "unique_engaged": 2,
            "engagement_percent": "50.0",
            "acknowledged": 2,
            "pending": 2,
            "acknowledgement_percent": "50.0",
            "departments": [
                {
                    "name": "Operations",
                    "recipients": 4,
                    "unique_views": 3,
                    "reach_percent": "75.0",
                    "acknowledged": 2,
                }
            ],
        }
    ]
    monkeypatch.setattr("apps.publications.views._analytics_metrics", lambda _request: rows)
    client = APIClient()
    client.force_authenticate(editor)

    response = client.get("/api/v1/editorial/analytics")
    export = client.get("/api/v1/editorial/analytics/departments.csv")

    assert response.status_code == 200
    department = response.data["departments"][0]
    assert department | {
        "reach_percent": str(department["reach_percent"]),
        "acknowledgement_percent": str(department["acknowledgement_percent"]),
    } == {
        "department": "Operations",
        "publications": 1,
        "recipients": 4,
        "views": 3,
        "acknowledged": 2,
        "reach_percent": "75.0",
        "acknowledgement_percent": "50.0",
    }
    assert export.status_code == 200
    assert export["Content-Disposition"] == 'attachment; filename="analytics-departments.csv"'
    assert "Operations,1,4,3,75.0,2,50.0" in export.content.decode("utf-8-sig")
