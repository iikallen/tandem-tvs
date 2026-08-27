import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, connection, connections, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.identity.models import AccessGrant, User
from apps.messenger.models import (
    Conversation,
    ConversationMembership,
    Message,
    MessageReaction,
    MessageRevision,
    PinnedMessage,
)
from apps.messenger.services import (
    add_group_member,
    change_group_role,
    create_direct_conversation,
    create_group_conversation,
    delete_message,
    leave_group,
    mark_delivered,
    pin_message,
    put_message_reaction,
    remove_group_member,
    send_message,
    unpin_message,
)
from apps.publications.models import AuditEvent, MediaAsset
from apps.realtime.models import RealtimeOutboxEvent
from apps.realtime.outbox import dispatch_pending_outbox
from apps.realtime.session_security import session_fingerprint


def user(username: str, *, news_editor: bool = False) -> User:
    account = User.objects.create(username=username, full_name=username.replace("-", " ").title())
    AccessGrant.objects.create(
        user=account,
        module=AccessGrant.Module.MESSENGER,
        role=AccessGrant.Role.MEMBER,
    )
    if news_editor:
        AccessGrant.objects.create(
            user=account,
            module=AccessGrant.Module.NEWS,
            role=AccessGrant.Role.EDITOR,
        )
    return account


def client(account: User) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=account)
    return api


def send(api: APIClient, conversation_id: object, body: str, **extra):
    return api.post(
        f"/api/v1/messenger/conversations/{conversation_id}/messages",
        {"client_message_id": str(uuid.uuid4()), "body": body, **extra},
        format="json",
    )


@pytest.mark.django_db
def test_membership_boundaries_hide_reply_and_pin_and_keep_historical_receipts():
    owner = user("stage8-owner")
    original = user("stage8-original")
    newcomer = user("stage8-newcomer")
    outsider = user("stage8-outsider")
    owner_client = client(owner)
    created = owner_client.post(
        "/api/v1/messenger/conversations/group",
        {"title": "Boundary group", "member_ids": [original.pk]},
        format="json",
    )
    assert created.status_code == 201
    conversation_id = created.data["id"]
    history_url = f"/api/v1/messenger/conversations/{conversation_id}/messages"
    first = send(owner_client, conversation_id, "Before join")
    assert first.status_code == 201
    assert owner_client.put(f"/api/v1/messenger/messages/{first.data['id']}/pin").status_code == 204

    members_url = f"/api/v1/messenger/conversations/{conversation_id}/members"
    added = owner_client.post(members_url, {"user_id": newcomer.pk}, format="json")
    assert added.status_code == 201
    newcomer_client = client(newcomer)
    assert newcomer_client.get(history_url).data["messages"] == []
    assert (
        newcomer_client.get(f"/api/v1/messenger/conversations/{conversation_id}").data[
            "pinned_messages"
        ]
        == []
    )
    hidden_reply = send(
        newcomer_client,
        conversation_id,
        "Hidden reply must fail",
        reply_to_id=first.data["id"],
    )
    assert hidden_reply.status_code == 404

    second = send(
        owner_client,
        conversation_id,
        "After join",
        reply_to_id=first.data["id"],
    )
    assert second.status_code == 201
    visible = newcomer_client.get(history_url).data["messages"]
    assert [message["sequence"] for message in visible] == [2]
    assert visible[0]["reply_to"] is None
    assert (
        newcomer_client.post(
            f"/api/v1/messenger/conversations/{conversation_id}/delivered",
            {"sequence": 2},
            format="json",
        ).status_code
        == 200
    )
    assert (
        newcomer_client.post(
            f"/api/v1/messenger/conversations/{conversation_id}/read",
            {"sequence": 2},
            format="json",
        ).status_code
        == 200
    )

    assert owner_client.delete(f"{members_url}/{original.pk}").status_code == 204
    third = send(owner_client, conversation_id, "After removal")
    assert third.status_code == 201
    assert client(original).get(history_url).status_code == 404
    direct = client(original).post(
        "/api/v1/messenger/conversations/direct",
        {"user_id": outsider.pk},
        format="json",
    )
    assert direct.status_code == 201
    forbidden_forward = send(
        client(original),
        direct.data["id"],
        "",
        forward_message_id=first.data["id"],
    )
    assert forbidden_forward.status_code == 404
    assert (
        owner_client.post(members_url, {"user_id": original.pk}, format="json").status_code == 201
    )
    rejoined = client(original).get(history_url)
    assert [message["sequence"] for message in rejoined.data["messages"]] == [1, 2]
    inbox = client(original).get("/api/v1/messenger/conversations")
    summary = next(row for row in inbox.data["results"] if row["id"] == conversation_id)
    assert summary["unread_count"] == 0

    receipts = owner_client.get(history_url).data["messages"]
    assert receipts[0]["receipt"]["recipient_count"] == 1
    assert receipts[1]["receipt"]["recipient_count"] == 2
    assert client(outsider).get(history_url).status_code == 404


@pytest.mark.django_db
def test_message_mutations_reactions_forward_search_state_and_group_admin_rules():
    owner = user("stage8-mutations-owner")
    member = user("stage8-mutations-member")
    outsider = user("stage8-mutations-outsider")
    owner_client = client(owner)
    member_client = client(member)
    conversation_id = owner_client.post(
        "/api/v1/messenger/conversations/group",
        {"title": "Mutation group", "member_ids": [member.pk]},
        format="json",
    ).data["id"]
    message = send(owner_client, conversation_id, "Original searchable text")
    message_url = f"/api/v1/messenger/messages/{message.data['id']}"

    assert member_client.get(message_url).data["body"] == "Original searchable text"
    assert client(outsider).get(message_url).status_code == 404
    assert member_client.patch(message_url, {"body": "stolen"}, format="json").status_code == 403
    edited = owner_client.patch(message_url, {"body": "Edited searchable text"}, format="json")
    assert edited.status_code == 200 and edited.data["edited_at"]
    assert MessageRevision.objects.filter(
        message_id=message.data["id"], body="Original searchable text"
    ).exists()
    revision = MessageRevision.objects.get(message_id=message.data["id"])
    with pytest.raises(ValidationError):
        revision.body = "rewritten"
        revision.save()
    with pytest.raises(ValidationError):
        MessageRevision.objects.filter(pk=revision.pk).delete()

    reaction_url = f"{message_url}/reaction"
    assert (
        member_client.put(reaction_url, {"reaction_type": "LIKE"}, format="json").status_code == 200
    )
    replaced = member_client.put(reaction_url, {"reaction_type": "LOVE"}, format="json")
    assert replaced.status_code == 200
    assert MessageReaction.objects.filter(message_id=message.data["id"], user=member).count() == 1
    assert replaced.data["reactions"] == [{"reaction_type": "LOVE", "count": 1, "mine": True}]
    assert (
        client(outsider).put(reaction_url, {"reaction_type": "LIKE"}, format="json").status_code
        == 404
    )
    assert member_client.delete(reaction_url).status_code == 204

    other, _ = create_direct_conversation(owner, outsider)
    foreign, _ = send_message(
        other,
        author=owner,
        client_message_id=uuid.uuid4(),
        body="Foreign source",
    )
    cross_reply = send(
        owner_client,
        conversation_id,
        "Cross reply",
        reply_to_id=foreign.pk,
    )
    assert cross_reply.status_code == 404
    forwarded = send(
        owner_client,
        conversation_id,
        "Forwarded",
        forward_message_id=foreign.pk,
    )
    assert forwarded.status_code == 201
    assert forwarded.data["forwarded_snapshot"] == {
        "author_name": owner.full_name,
        "body": "Foreign source",
        "created_at": foreign.created_at.isoformat(),
    }

    state_url = f"/api/v1/messenger/conversations/{conversation_id}/state"
    state = owner_client.patch(
        state_url,
        {
            "is_archived": True,
            "pinned": True,
            "muted_until": "2030-01-01T00:00:00Z",
            "draft_body": "device draft",
        },
        format="json",
    )
    assert state.status_code == 200
    owner_state = ConversationMembership.objects.get(
        conversation_id=conversation_id, user=owner, left_at__isnull=True
    )
    member_state = ConversationMembership.objects.get(
        conversation_id=conversation_id, user=member, left_at__isnull=True
    )
    assert (
        owner_state.is_archived
        and owner_state.pinned_at
        and owner_state.draft_body == "device draft"
    )
    assert (
        not member_state.is_archived
        and member_state.pinned_at is None
        and not member_state.draft_body
    )
    assert (
        owner_client.get("/api/v1/messenger/conversations").data["results"][0]["id"]
        == conversation_id
    )

    search_url = f"/api/v1/messenger/conversations/{conversation_id}/search?q=searchable"
    assert [row["id"] for row in owner_client.get(search_url).data["results"]] == [
        message.data["id"]
    ]
    deleted = owner_client.delete(message_url)
    assert deleted.status_code == 200 and deleted.data["body"] == "" and deleted.data["deleted_at"]
    assert owner_client.get(search_url).data["results"] == []

    assert (
        owner_client.patch(
            f"{members_url(conversation_id)}/{member.pk}",
            {"role": "ADMIN"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        owner_client.post(f"/api/v1/messenger/conversations/{conversation_id}/leave").status_code
        == 204
    )
    assert owner_client.get(f"/api/v1/messenger/conversations/{conversation_id}").status_code == 404


def members_url(conversation_id: object) -> str:
    return f"/api/v1/messenger/conversations/{conversation_id}/members"


@pytest.mark.django_db
def test_attachment_download_requires_visible_message_membership(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    owner = user("stage8-file-owner")
    member = user("stage8-file-member")
    outsider = user("stage8-file-outsider")
    editor = user("stage8-file-editor", news_editor=True)
    owner_client = client(owner)
    conversation, _ = create_direct_conversation(owner, member)
    upload = owner_client.post(
        f"/api/v1/messenger/conversations/{conversation.pk}/attachments",
        {
            "file": SimpleUploadedFile(
                "brief.pdf", b"%PDF-1.7\n%%EOF\n", content_type="application/pdf"
            )
        },
        format="multipart",
    )
    assert upload.status_code == 201
    asset_id = upload.data["id"]
    assert MediaAsset.objects.get(pk=asset_id).temporary_until is not None
    content_url = f"/api/v1/media/{asset_id}/content"
    assert client(member).get(content_url).status_code == 404
    assert client(editor).get(content_url).status_code == 404
    editorial_assets = client(editor).get("/api/v1/editorial/media")
    assert asset_id not in {row["id"] for row in editorial_assets.data["results"]}
    assert client(editor).delete(f"/api/v1/editorial/media/{asset_id}").status_code == 404
    attached = owner_client.post(
        f"/api/v1/messenger/conversations/{conversation.pk}/messages",
        {"client_message_id": str(uuid.uuid4()), "attachment_ids": [asset_id]},
        format="json",
    )
    assert attached.status_code == 201
    assert MediaAsset.objects.get(pk=asset_id).temporary_until is None
    assert attached.data["attachments"][0]["id"] == asset_id
    assert client(member).get(content_url).status_code == 200
    assert client(outsider).get(content_url).status_code == 404
    assert client(editor).get(content_url).status_code == 404

    MediaAsset.objects.filter(pk=asset_id).update(status=MediaAsset.Status.PENDING_SCAN)
    rejected = owner_client.post(
        f"/api/v1/messenger/conversations/{conversation.pk}/messages",
        {"client_message_id": str(uuid.uuid4()), "attachment_ids": [asset_id]},
        format="json",
    )
    assert rejected.status_code == 403
    MediaAsset.objects.filter(pk=asset_id).update(status=MediaAsset.Status.READY)
    assert (
        owner_client.delete(f"/api/v1/messenger/messages/{attached.data['id']}").status_code == 200
    )
    assert client(member).get(content_url).status_code == 404


@pytest.mark.django_db
def test_rejoined_member_can_download_only_attachments_from_visible_intervals(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    owner = user("stage8-file-rejoin-owner")
    member = user("stage8-file-rejoin-member")
    conversation = create_group_conversation(owner, title="Intervals", members=[member])
    owner_client = client(owner)
    member_client = client(member)

    def upload_and_send(name: str) -> str:
        upload = owner_client.post(
            f"/api/v1/messenger/conversations/{conversation.pk}/attachments",
            {
                "file": SimpleUploadedFile(
                    name, b"%PDF-1.7\n%%EOF\n", content_type="application/pdf"
                )
            },
            format="multipart",
        )
        assert upload.status_code == 201
        response = owner_client.post(
            f"/api/v1/messenger/conversations/{conversation.pk}/messages",
            {
                "client_message_id": str(uuid.uuid4()),
                "attachment_ids": [upload.data["id"]],
            },
            format="json",
        )
        assert response.status_code == 201
        return upload.data["id"]

    first_asset = upload_and_send("first.pdf")
    remove_group_member(conversation, actor=owner, user=member)
    hidden_asset = upload_and_send("hidden.pdf")
    add_group_member(conversation, actor=owner, user=member)
    current_asset = upload_and_send("current.pdf")

    assert member_client.get(f"/api/v1/media/{first_asset}/content").status_code == 200
    assert member_client.get(f"/api/v1/media/{hidden_asset}/content").status_code == 404
    assert member_client.get(f"/api/v1/media/{current_asset}/content").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_concurrent_exact_retry_creates_one_message_and_conflict_is_422():
    owner = user("stage8-retry-owner")
    peer = user("stage8-retry-peer")
    conversation, _ = create_direct_conversation(owner, peer)
    client_message_id = uuid.uuid4()

    def retry():
        close_old_connections()
        try:
            return send_message(
                Conversation.objects.get(pk=conversation.pk),
                author=User.objects.get(pk=owner.pk),
                client_message_id=client_message_id,
                body="same payload",
            )[0].pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _index: retry(), range(4)))
    assert len(set(ids)) == 1
    assert Message.objects.filter(conversation=conversation).count() == 1
    conflict = client(owner).post(
        f"/api/v1/messenger/conversations/{conversation.pk}/messages",
        {"client_message_id": str(client_message_id), "body": "different payload"},
        format="json",
    )
    assert conflict.status_code == 422
    assert conflict.data["error"]["code"] == "idempotency_conflict"


@pytest.mark.django_db(transaction=True)
def test_outbox_recovers_after_delivery_failure_and_event_has_no_message_content(monkeypatch):
    owner = user("stage8-outbox-owner")
    peer = user("stage8-outbox-peer")
    conversation, _ = create_direct_conversation(owner, peer)
    RealtimeOutboxEvent.objects.all().delete()

    class FailingLayer:
        async def group_send(self, _group, _event):
            raise RuntimeError("Redis unavailable")

    monkeypatch.setattr("apps.realtime.outbox.get_channel_layer", lambda: FailingLayer())
    message, _ = send_message(
        conversation,
        author=owner,
        client_message_id=uuid.uuid4(),
        body="must remain private",
    )
    pending = RealtimeOutboxEvent.objects.get(delivered_at__isnull=True)
    assert pending.payload["event_id"] == str(pending.pk)
    assert "must remain private" not in str(pending.payload)

    delivered = []

    class WorkingLayer:
        async def group_send(self, group, event):
            delivered.append((group, event))

    monkeypatch.setattr("apps.realtime.outbox.get_channel_layer", lambda: WorkingLayer())
    RealtimeOutboxEvent.objects.filter(pk=pending.pk).update(available_at=timezone.now())
    assert dispatch_pending_outbox() == 1
    pending.refresh_from_db()
    assert pending.delivered_at is not None
    assert delivered[0][1]["event"]["message_id"] == str(message.pk)


@pytest.mark.django_db
def test_inbox_keeps_500_conversations_reachable_without_prefetching_large_groups():
    owner = user("stage8-inbox-owner")
    peer = user("stage8-inbox-peer")
    conversations = [
        Conversation(type=Conversation.Type.DIRECT, created_by=owner) for _ in range(500)
    ]
    Conversation.objects.bulk_create(conversations)
    ConversationMembership.objects.bulk_create(
        [
            membership
            for conversation in conversations
            for membership in (
                ConversationMembership(conversation=conversation, user=owner),
                ConversationMembership(conversation=conversation, user=peer),
            )
        ]
    )
    group_members = [
        User(username=f"stage8-large-{number}", full_name=f"Large {number}")
        for number in range(200)
    ]
    User.objects.bulk_create(group_members)
    groups = [
        Conversation(type=Conversation.Type.GROUP, title=f"Large {number}", created_by=owner)
        for number in range(50)
    ]
    Conversation.objects.bulk_create(groups)
    ConversationMembership.objects.bulk_create(
        [
            ConversationMembership(conversation=group, user=account)
            for group in groups
            for account in [owner, *group_members]
        ]
    )

    api = client(owner)
    with CaptureQueriesContext(connection) as queries:
        response = api.get("/api/v1/messenger/conversations")
    assert response.status_code == 200 and len(response.data["results"]) == 30
    assert len(queries) <= 10, [query["sql"] for query in queries]
    seen: set[str] = set()
    while True:
        seen.update(row["id"] for row in response.data["results"])
        if not response.data["next"]:
            break
        response = api.get(response.data["next"])
    assert len(seen) == 550
    assert all("members" not in row for row in response.data["results"])


@pytest.mark.django_db
def test_messenger_audit_is_append_only_for_stage8_mutations():
    owner = user("stage8-audit-owner")
    peer = user("stage8-audit-peer")
    conversation, _ = create_direct_conversation(owner, peer)
    message, _ = send_message(
        conversation,
        author=owner,
        client_message_id=uuid.uuid4(),
        body="audit me",
    )
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.Type.MESSENGER_MESSAGE_SENT,
        target_type=AuditEvent.TargetType.MESSAGE,
        target_id=str(message.pk),
        actor=owner,
    ).exists()
    event = AuditEvent.objects.get(
        event_type=AuditEvent.Type.MESSENGER_MESSAGE_SENT, target_id=str(message.pk)
    )
    with pytest.raises(ValidationError):
        event.delete()


def test_realtime_outbox_is_scheduled_every_two_seconds(settings):
    assert settings.CELERY_BEAT_SCHEDULE["dispatch-realtime-outbox"] == {
        "task": "realtime.dispatch-outbox",
        "schedule": 2.0,
    }


@pytest.mark.django_db
def test_recovery_email_is_case_insensitively_unique_and_capability_urls_use_fragments(
    monkeypatch,
):
    admin = user("stage8-platform-admin")
    AccessGrant.objects.create(
        user=admin,
        module=AccessGrant.Module.PLATFORM,
        role=AccessGrant.Role.ADMIN,
    )
    existing = User.objects.create(
        username="stage8-existing-email",
        full_name="Existing Email",
        email=" Person@Example.Invalid ",
    )
    assert existing.email == "person@example.invalid"
    api = client(admin)
    duplicate = api.post(
        "/api/v1/platform/users",
        {
            "username": "stage8-duplicate-email",
            "full_name": "Duplicate Email",
            "email": " Person@Example.Invalid ",
        },
        format="json",
    )
    assert duplicate.status_code == 400
    assert duplicate.data["email"]
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(
            username="stage8-db-duplicate",
            full_name="DB Duplicate",
            email="PERSON@example.invalid",
        )
    own_email = api.patch(
        f"/api/v1/platform/users/{existing.pk}",
        {"email": " Person@Example.Invalid "},
        format="json",
    )
    assert own_email.status_code == 200 and own_email.data["email"] == "person@example.invalid"
    other = User.objects.create(
        username="stage8-other-email",
        full_name="Other Email",
        email="other@example.invalid",
    )
    duplicate_update = api.patch(
        f"/api/v1/platform/users/{other.pk}",
        {"email": "PERSON@example.invalid"},
        format="json",
    )
    assert duplicate_update.status_code == 400 and duplicate_update.data["email"]

    pending = api.post(
        "/api/v1/platform/users",
        {"username": "stage8-pending", "full_name": "Pending User"},
        format="json",
    )
    invitation = api.post(f"/api/v1/platform/users/{pending.data['id']}/invitation")
    assert invitation.status_code == 200
    assert invitation.data["activation_url"].startswith("/activate#token=")
    assert "?token=" not in invitation.data["activation_url"]

    existing.activated_at = timezone.now()
    existing.save(update_fields=["activated_at"])
    reset = api.post(f"/api/v1/platform/users/{existing.pk}/password-reset")
    assert reset.status_code == 200
    assert reset.data["reset_url"].startswith("/reset-password#token=")
    assert "?token=" not in reset.data["reset_url"]

    observed: list[str] = []
    monkeypatch.setattr("apps.realtime.events.invalidate_session", observed.append)
    monkeypatch.setattr(
        "apps.discussions.views.create_realtime_ticket",
        lambda **_kwargs: ("ticket", 30),
    )
    session_api = client(admin)
    ticket = session_api.post("/api/v1/realtime/tickets", {"scope": "MESSENGER"}, format="json")
    assert ticket.status_code == 200
    session_key = session_api.session.session_key
    assert session_key
    assert session_api.post("/api/v1/auth/logout").status_code == 204
    assert observed == [session_fingerprint(session_key)]


@pytest.mark.django_db
def test_stage8_service_guards_and_idempotent_mutation_branches():
    owner = user("stage8-guards-owner")
    member = user("stage8-guards-member")
    third = user("stage8-guards-third")
    direct_conversation, _ = create_direct_conversation(owner, member)
    direct_membership = ConversationMembership.objects.get(
        conversation=direct_conversation, user=owner
    )
    direct_membership.role = ConversationMembership.Role.ADMIN
    direct_membership.save(update_fields=["role"])
    for operation in (
        lambda: add_group_member(direct_conversation, actor=owner, user=third),
        lambda: remove_group_member(direct_conversation, actor=owner, user=member),
        lambda: change_group_role(
            direct_conversation,
            actor=owner,
            user=member,
            role=ConversationMembership.Role.ADMIN,
        ),
        lambda: leave_group(direct_conversation, user=owner),
    ):
        with pytest.raises(ValidationError):
            operation()

    group = client(owner).post(
        "/api/v1/messenger/conversations/group",
        {"title": "Guard group", "member_ids": [member.pk]},
        format="json",
    )
    conversation = Conversation.objects.get(pk=group.data["id"])
    message, _ = send_message(
        conversation,
        author=owner,
        client_message_id=uuid.uuid4(),
        body="Guarded",
    )
    assert (
        mark_delivered(conversation, user=member, sequence=message.sequence).last_delivered_sequence
        == 1
    )
    assert mark_delivered(conversation, user=member, sequence=0).last_delivered_sequence == 1
    with pytest.raises(ValidationError):
        mark_delivered(conversation, user=member, sequence=2)
    with pytest.raises(PermissionDenied):
        add_group_member(conversation, actor=member, user=third)
    with pytest.raises(ValidationError):
        add_group_member(conversation, actor=owner, user=member)
    with pytest.raises(ValidationError):
        change_group_role(
            conversation,
            actor=owner,
            user=owner,
            role=ConversationMembership.Role.MEMBER,
        )
    with pytest.raises(ValidationError):
        remove_group_member(conversation, actor=owner, user=owner)
    with pytest.raises(ValidationError):
        leave_group(conversation, user=owner)
    with pytest.raises(PermissionDenied):
        pin_message(message, actor=member)

    direct_message, _ = send_message(
        direct_conversation,
        author=owner,
        client_message_id=uuid.uuid4(),
        body="Pin then remove",
    )
    pin_message(direct_message, actor=member)
    assert unpin_message(direct_message, actor=member) is True
    assert unpin_message(direct_message, actor=member) is False
    assert not PinnedMessage.objects.filter(message=direct_message).exists()
    with pytest.raises(PermissionDenied):
        delete_message(direct_message, actor=member)
    deleted = delete_message(direct_message, actor=owner)
    assert delete_message(deleted, actor=owner) == deleted
    with pytest.raises(ValidationError):
        pin_message(deleted, actor=member)
    with pytest.raises(ValidationError):
        put_message_reaction(deleted, user=member, reaction_type=MessageReaction.Type.LIKE)
