import uuid

import pytest
from rest_framework.test import APIClient

from apps.identity.models import AccessGrant, User
from apps.messenger.models import (
    Conversation,
    ConversationMembership,
    Message,
    MessageReport,
    MessageRevision,
    MessengerRestriction,
)
from apps.publications.models import AuditEvent


def account(
    username: str,
    *,
    module: str = AccessGrant.Module.MESSENGER,
    role: str = AccessGrant.Role.MEMBER,
) -> User:
    user = User.objects.create(username=username, full_name=username)
    AccessGrant.objects.create(user=user, module=module, role=role)
    return user


def api(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def conversation_with_message(*members: User) -> tuple[Conversation, Message]:
    conversation = Conversation.objects.create(
        type=Conversation.Type.GROUP,
        title="Report test",
        created_by=members[0],
        last_sequence=1,
    )
    ConversationMembership.objects.bulk_create(
        [
            ConversationMembership(
                conversation=conversation,
                user=user,
                role=(
                    ConversationMembership.Role.ADMIN
                    if user == members[0]
                    else ConversationMembership.Role.MEMBER
                ),
            )
            for user in members
        ]
    )
    message = Message.objects.create(
        conversation=conversation,
        sequence=1,
        client_message_id=uuid.uuid4(),
        author=members[0],
        body="Reported private message",
        request_fingerprint="f" * 64,
    )
    return conversation, message


@pytest.mark.django_db
def test_message_report_create_deduplicates_and_enforces_membership_interval():
    owner = account("report-owner")
    peer = account("report-peer")
    outsider = account("report-outsider")
    newcomer = account("report-newcomer")
    conversation, message = conversation_with_message(owner, peer)
    url = f"/api/v1/messenger/messages/{message.pk}/report"

    first = api(peer).post(url, {"reason": "abuse"}, format="json")
    duplicate = api(peer).post(url, {"reason": "replacement"}, format="json")
    assert (first.status_code, duplicate.status_code, MessageReport.objects.count()) == (
        201,
        200,
        1,
    )
    assert MessageReport.objects.get().reason == "abuse"
    assert (
        AuditEvent.objects.filter(
            event_type=AuditEvent.Type.MESSENGER_MESSAGE_REPORTED,
            target_type=AuditEvent.TargetType.MESSAGE,
            target_id=str(message.pk),
        ).count()
        == 1
    )

    assert api(outsider).post(url, {"reason": "idor"}, format="json").status_code == 404
    ConversationMembership.objects.create(
        conversation=conversation,
        user=newcomer,
        joined_sequence=message.sequence,
    )
    assert api(newcomer).post(url, {"reason": "history idor"}, format="json").status_code == 404


@pytest.mark.django_db
def test_messenger_moderators_queue_decisions_and_private_message_boundary():
    owner = account("decision-owner")
    peer = account("decision-peer")
    moderator = account("decision-moderator", role=AccessGrant.Role.MODERATOR)
    admin = account("decision-admin", role=AccessGrant.Role.ADMIN)
    platform_admin = account(
        "decision-platform-admin",
        module=AccessGrant.Module.PLATFORM,
        role=AccessGrant.Role.ADMIN,
    )
    conversation, message = conversation_with_message(owner, peer)
    restricted_message = Message.objects.create(
        conversation=conversation,
        sequence=2,
        client_message_id=uuid.uuid4(),
        author=peer,
        body="Restriction candidate",
        request_fingerprint="r" * 64,
    )
    dismissed_message = Message.objects.create(
        conversation=conversation,
        sequence=3,
        client_message_id=uuid.uuid4(),
        author=owner,
        body="Leave unchanged",
        request_fingerprint="d" * 64,
    )
    conversation.last_sequence = 3
    conversation.save(update_fields=["last_sequence"])
    report_url = f"/api/v1/messenger/messages/{message.pk}/report"
    first = api(owner).post(report_url, {"reason": "first"}, format="json")
    second = api(peer).post(
        f"/api/v1/messenger/messages/{dismissed_message.pk}/report",
        {"reason": "second"},
        format="json",
    )
    restricted = api(owner).post(
        f"/api/v1/messenger/messages/{restricted_message.pk}/report",
        {"reason": "restrict author"},
        format="json",
    )
    queue_url = "/api/v1/messenger/moderation/reports"

    queue = api(moderator).get(queue_url)
    assert queue.status_code == 200
    assert {item["message"]["body"] for item in queue.data["reports"]} == {
        "Reported private message",
        "Restriction candidate",
        "Leave unchanged",
    }
    assert api(owner).get(queue_url).status_code == 403
    assert api(platform_admin).get(queue_url).status_code == 403
    assert api(platform_admin).get(f"/api/v1/messenger/messages/{message.pk}").status_code == 403

    for actor, report_id, decision in (
        (moderator, first.data["id"], MessageReport.Decision.MESSAGE_DELETED),
        (admin, second.data["id"], MessageReport.Decision.DISMISSED),
    ):
        response = api(actor).post(
            f"/api/v1/messenger/moderation/reports/{report_id}/resolve",
            {"decision": decision, "note": "reviewed"},
            format="json",
        )
        assert response.status_code == 200
        report = MessageReport.objects.get(pk=report_id)
        assert (report.state, report.decision, report.moderated_by, report.moderator_note) == (
            MessageReport.State.RESOLVED,
            decision,
            actor,
            "reviewed",
        )
        assert report.moderated_at is not None

    message.refresh_from_db()
    assert message.deleted_at is not None and message.body == ""
    assert MessageRevision.objects.filter(message=message, edited_by=moderator).count() == 1
    dismissed_message.refresh_from_db()
    assert dismissed_message.deleted_at is None and dismissed_message.body == "Leave unchanged"

    restriction_response = api(admin).post(
        f"/api/v1/messenger/moderation/reports/{restricted.data['id']}/resolve",
        {
            "decision": MessageReport.Decision.AUTHOR_RESTRICTED,
            "note": "temporary restriction",
            "restriction_hours": 2,
        },
        format="json",
    )
    assert restriction_response.status_code == 200
    restriction = MessengerRestriction.objects.get(user=peer)
    assert restriction.created_by == admin and restriction.expires_at is not None
    assert (
        api(peer)
        .post(
            f"/api/v1/messenger/conversations/{conversation.pk}/messages",
            {"client_message_id": str(uuid.uuid4()), "body": "must be blocked"},
            format="json",
        )
        .status_code
        == 403
    )

    assert (
        AuditEvent.objects.filter(
            event_type=AuditEvent.Type.MESSENGER_REPORT_RESOLVED,
            target_type=AuditEvent.TargetType.REPORT,
        ).count()
        == 3
    )
    assert (
        AuditEvent.objects.filter(
            event_type=AuditEvent.Type.MESSENGER_USER_RESTRICTED,
            target_type=AuditEvent.TargetType.USER,
            target_id=str(peer.pk),
        ).count()
        == 1
    )
    assert (
        api(moderator)
        .post(
            f"/api/v1/messenger/moderation/reports/{first.data['id']}/resolve",
            {"decision": MessageReport.Decision.DISMISSED},
            format="json",
        )
        .status_code
        == 400
    )
    assert (
        api(owner)
        .post(
            f"/api/v1/messenger/moderation/reports/{first.data['id']}/resolve",
            {"decision": MessageReport.Decision.DISMISSED},
            format="json",
        )
        .status_code
        == 403
    )
