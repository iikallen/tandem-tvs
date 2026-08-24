from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.utils import timezone
from rest_framework.test import APIClient

from apps.discussions.models import (
    Comment,
    CommentAttachment,
    CommentMention,
    CommentReport,
    CommentRestriction,
    EngagementSettings,
    ModerationFlag,
    Notification,
    Reaction,
    StopWord,
)
from apps.discussions.services import (
    create_comment,
    delete_comment,
    delete_reaction,
    moderate_comment,
    normalize_stop_word,
    put_reaction,
    update_comment,
)
from apps.identity.models import User
from apps.organization.models import OrgUnit
from apps.publications.engagement import (
    acknowledge,
    csv_text,
    publication_metrics,
    publication_metrics_bulk,
    refresh_recipient_snapshot,
    resolve_recipient_users,
    safe_csv_cell,
)
from apps.publications.media import can_read_media
from apps.publications.models import (
    Acknowledgement,
    AudienceRule,
    AuditEvent,
    Category,
    MediaAsset,
    Publication,
    PublicationView,
)


def call(client, settings, portal_id, method, path, data=None):
    settings.MOCK_PORTAL_USER_ID = portal_id
    return getattr(client, method)(path, data, format="json")


@pytest.fixture
def stage5(db, settings):
    client = APIClient()
    for portal_id in ("employee-1", "author-1", "editor-1", "admin-1"):
        assert call(client, settings, portal_id, "get", "/api/v1/me").status_code == 200
    editor = User.objects.get(portal_id="editor-1")
    employee = User.objects.get(portal_id="employee-1")
    category = Category.objects.create(
        slug="stage5", name="Stage 5", comment_attachments_enabled=True
    )
    publication = Publication.objects.create(
        title="Stage 5",
        slug="stage-5",
        summary="Engagement",
        body={"type": "doc", "content": [{"type": "paragraph", "content": []}]},
        category=category,
        author=editor,
        status=Publication.Status.PUBLISHED,
        published_at=timezone.now() - timedelta(minutes=1),
        acknowledgement_required=True,
    )
    AudienceRule.objects.create(publication=publication, kind=AudienceRule.Kind.ALL)
    asset = MediaAsset.objects.create(
        original_name="guide.pdf",
        storage_key="assets/stage5-guide.pdf",
        file="assets/stage5-guide.pdf",
        mime_type="application/pdf",
        size=100,
        sha256="a" * 64,
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=employee,
    )
    return client, publication, asset


@pytest.mark.django_db
def test_threads_mentions_attachments_notifications_stop_words_and_policy(stage5, settings):
    client, publication, asset = stage5
    base = f"/api/v1/news/{publication.pk}/comments"
    settings_path = "/api/v1/editorial/settings/engagement"
    assert call(client, settings, "employee-1", "get", settings_path).status_code == 403
    configured = call(
        client,
        settings,
        "admin-1",
        "patch",
        settings_path,
        {
            "comment_edit_window_minutes": 60,
            "comment_delete_window_minutes": 60,
            "enabled_reaction_types": ["LIKE", "INSIGHTFUL"],
            "max_comment_attachments": 2,
            "max_comment_attachment_bytes": 1000,
        },
    )
    assert configured.status_code == 200
    assert configured.data["enabled_reaction_types"] == ["LIKE", "INSIGHTFUL"]
    stop = call(
        client,
        settings,
        "admin-1",
        "post",
        f"{settings_path}/stop-words",
        {"value": "СПАМ"},
    )
    assert stop.status_code == 201
    assert normalize_stop_word("  ＳＰＡＭ  ") == "spam"
    assert (
        call(
            client,
            settings,
            "admin-1",
            "patch",
            f"{settings_path}/stop-words/{stop.data['id']}",
            {"is_active": True},
        ).status_code
        == 200
    )

    foreign_asset = MediaAsset.objects.create(
        original_name="private.pdf",
        storage_key="assets/private-stage5.pdf",
        file="assets/private-stage5.pdf",
        mime_type="application/pdf",
        size=100,
        sha256="b" * 64,
        kind=MediaAsset.Kind.DOCUMENT,
        uploader=User.objects.get(portal_id="editor-1"),
    )
    assert (
        call(
            client,
            settings,
            "employee-1",
            "post",
            base,
            {"body": "IDOR", "attachments": [str(foreign_asset.pk)]},
        ).status_code
        == 400
    )

    root = call(
        client,
        settings,
        "employee-1",
        "post",
        base,
        {"body": "СПАМ: изучите файл", "mentions": ["admin-1"], "attachments": [str(asset.pk)]},
    )
    assert root.status_code == 201
    root_id = root.data["id"]
    assert root.data["attachments"][0]["id"] == str(asset.pk)
    assert CommentMention.objects.filter(comment_id=root_id).count() == 1
    assert CommentAttachment.objects.filter(comment_id=root_id).count() == 1
    assert ModerationFlag.objects.filter(comment_id=root_id).count() == 1
    notification = Notification.objects.get(recipient__portal_id="admin-1", comment_id=root_id)
    assert str(notification).endswith("COMMENT_MENTION")

    reply = call(
        client,
        settings,
        "editor-1",
        "post",
        base,
        {"body": "Первый ответ", "reply_to": root_id},
    )
    assert reply.status_code == 201
    nested = call(
        client,
        settings,
        "admin-1",
        "post",
        base,
        {"body": "Ответ на ответ", "reply_to": reply.data["id"], "mentions": ["editor-1"]},
    )
    assert nested.status_code == 201
    assert nested.data["thread_root"] == root_id
    assert nested.data["reply_to"] == reply.data["id"]
    assert (
        Notification.objects.filter(
            comment_id=nested.data["id"], recipient__portal_id="editor-1"
        ).count()
        == 1
    )

    roots = call(client, settings, "employee-1", "get", f"{base}?sort=popular")
    assert roots.status_code == 200
    assert roots.data["results"][0]["reply_count"] == 2
    assert len(roots.data["results"][0]["preview_replies"]) == 2
    replies = call(client, settings, "employee-1", "get", f"{base}/{root_id}/replies")
    assert [row["body"] for row in replies.data["results"]] == ["Первый ответ", "Ответ на ответ"]
    assert call(client, settings, "employee-1", "get", f"{base}?sort=wrong").status_code == 400
    candidates = call(
        client,
        settings,
        "employee-1",
        "get",
        f"/api/v1/news/{publication.pk}/mention-candidates?search=Дмит",
    )
    assert candidates.data[0]["portal_id"] == "editor-1"

    notifications = call(client, settings, "admin-1", "get", "/api/v1/notifications")
    assert notifications.status_code == 200
    assert (
        call(
            client, settings, "admin-1", "post", f"/api/v1/notifications/{notification.pk}/read"
        ).status_code
        == 204
    )
    notification.refresh_from_db()
    assert notification.read_at is not None
    assert (
        call(
            client, settings, "employee-1", "post", f"/api/v1/notifications/{notification.pk}/read"
        ).status_code
        == 404
    )

    publication.comments_enabled = False
    publication.save(update_fields=["comments_enabled"])
    assert call(client, settings, "employee-1", "post", base, {"body": "closed"}).status_code == 403
    publication.comments_enabled = True
    publication.save(update_fields=["comments_enabled"])
    category = publication.category
    category.comment_attachments_enabled = False
    category.save(update_fields=["comment_attachments_enabled"])
    denied = call(
        client,
        settings,
        "employee-1",
        "post",
        base,
        {"body": "file", "attachments": [str(asset.pk)]},
    )
    assert denied.status_code == 400


@pytest.mark.django_db
def test_reactions_reports_moderation_restrictions_and_windows(stage5, settings):
    client, publication, _asset = stage5
    EngagementSettings.objects.create(pk=1, enabled_reaction_types=["LIKE", "CELEBRATE"])
    base = f"/api/v1/news/{publication.pk}"
    comment = call(
        client, settings, "employee-1", "post", f"{base}/comments", {"body": "Review me"}
    )
    comment_id = comment.data["id"]

    assert call(client, settings, "employee-1", "put", f"{base}/reactions/LIKE").status_code == 201
    assert (
        call(client, settings, "employee-1", "put", f"{base}/reactions/CELEBRATE").status_code
        == 200
    )
    assert Reaction.objects.filter(publication=publication).count() == 1
    assert Reaction.objects.get(publication=publication).reaction_type == "CELEBRATE"
    assert (
        call(client, settings, "employee-1", "put", f"{base}/reactions/THANKS").status_code == 400
    )
    comment_reaction = f"{base}/comments/{comment_id}/reactions"
    assert call(client, settings, "admin-1", "put", f"{comment_reaction}/LIKE").status_code == 201
    assert call(client, settings, "employee-1", "get", comment_reaction).data["counts"] == {
        "LIKE": 1
    }
    assert (
        call(client, settings, "admin-1", "delete", f"{comment_reaction}/LIKE").status_code == 204
    )

    report_path = f"{base}/comments/{comment_id}/reports"
    first = call(client, settings, "editor-1", "post", report_path, {"reason": "Policy"})
    second = call(client, settings, "editor-1", "post", report_path, {"reason": "Again"})
    assert (first.status_code, second.status_code, CommentReport.objects.count()) == (201, 200, 1)
    assert (
        call(client, settings, "employee-1", "get", "/api/v1/editorial/moderation").status_code
        == 403
    )
    queue = call(client, settings, "admin-1", "get", "/api/v1/editorial/moderation")
    assert queue.status_code == 200 and len(queue.data["reports"]) == 1
    action = f"/api/v1/editorial/moderation/comments/{comment_id}"
    assert call(client, settings, "admin-1", "post", f"{action}/hide").data["body"] is None
    stored = Comment.objects.get(pk=comment_id)
    assert stored.body == "Review me"
    assert not can_read_media(User.objects.get(portal_id="employee-1"), _asset)
    assert (
        call(client, settings, "admin-1", "post", f"{action}/restore").data["body"] == "Review me"
    )
    assert call(client, settings, "admin-1", "post", f"{action}/remove").data["status"] == "REMOVED"
    assert AuditEvent.objects.filter(target_id=comment_id).count() == 3
    report = CommentReport.objects.get()
    assert (
        call(
            client,
            settings,
            "admin-1",
            "post",
            f"/api/v1/editorial/moderation/reports/{report.pk}/resolve",
        ).status_code
        == 204
    )

    restriction = "/api/v1/editorial/moderation/users/author-1/restriction"
    assert (
        call(
            client, settings, "admin-1", "post", restriction, {"hours": 24, "reason": "spam"}
        ).status_code
        == 201
    )
    assert (
        call(
            client, settings, "author-1", "post", f"{base}/comments", {"body": "blocked"}
        ).status_code
        == 403
    )
    assert call(client, settings, "admin-1", "delete", restriction).status_code == 204
    assert (
        call(
            client, settings, "author-1", "post", f"{base}/comments", {"body": "allowed"}
        ).status_code
        == 201
    )
    assert call(client, settings, "admin-1", "post", restriction, {"hours": 0}).status_code == 400

    active = Comment.objects.filter(author__portal_id="author-1").latest("created_at")
    active.created_at = timezone.now() - timedelta(minutes=61)
    active.save(update_fields=["created_at"])
    detail = f"{base}/comments/{active.pk}"
    assert call(client, settings, "author-1", "patch", detail, {"body": "late"}).status_code == 403
    assert call(client, settings, "author-1", "delete", detail).status_code == 403


@pytest.mark.django_db
def test_recipient_acknowledgement_analytics_lists_csv_and_parity(
    stage5, settings, django_assert_num_queries
):
    client, publication, _asset = stage5
    rows = refresh_recipient_snapshot(publication)
    assert len(rows) == 4
    with django_assert_num_queries(2):
        resolved_ids = {user.pk for user in resolve_recipient_users(publication)}
    assert resolved_ids == {row.user.pk for row in rows}
    assert str(rows[0]).startswith(str(publication.pk))
    for portal_id in ("employee-1", "author-1"):
        response = call(
            client, settings, portal_id, "post", f"/api/v1/news/{publication.pk}/acknowledgement"
        )
        assert response.status_code == 201
        assert (
            call(
                client,
                settings,
                portal_id,
                "post",
                f"/api/v1/news/{publication.pk}/acknowledgement",
            ).status_code
            == 200
        )
    assert Acknowledgement.objects.count() == 2
    first_ack = Acknowledgement.objects.first()
    assert first_ack is not None
    assert str(first_ack).startswith(str(publication.pk))
    with pytest.raises(ValidationError):
        first_ack.save()
    with pytest.raises(ValidationError):
        first_ack.delete()
    with pytest.raises(ValidationError):
        Acknowledgement.objects.all().update(user=first_ack.user)
    with pytest.raises(ValidationError):
        Acknowledgement.objects.all().delete()

    now = timezone.now()
    for portal_id in ("employee-1", "author-1", "editor-1"):
        user = User.objects.get(portal_id=portal_id)
        PublicationView.objects.create(
            publication=publication, user=user, first_viewed_at=now, last_viewed_at=now
        )
    comment = Comment.objects.create(
        publication=publication, author=User.objects.get(portal_id="employee-1"), body="Metric"
    )
    Reaction.objects.create(
        publication=publication, user=User.objects.get(portal_id="admin-1"), reaction_type="LIKE"
    )
    Reaction.objects.create(
        comment=comment, user=User.objects.get(portal_id="author-1"), reaction_type="LIKE"
    )
    metrics = publication_metrics(publication)
    assert metrics["recipients"] == 4
    assert metrics["unique_views"] == 3
    assert str(metrics["reach_percent"]) == "75.0"
    assert metrics["unique_engaged"] == 3
    assert str(metrics["engagement_percent"]) == "75.0"
    assert str(metrics["acknowledgement_percent"]) == "50.0"
    assert metrics["departments"]
    with django_assert_num_queries(6):
        assert publication_metrics_bulk([publication]) == [metrics]

    analytics = call(
        client,
        settings,
        "editor-1",
        "get",
        f"/api/v1/editorial/publications/{publication.pk}/analytics",
    )
    assert analytics.data["recipients"] == 4
    aggregate = call(
        client, settings, "editor-1", "get", "/api/v1/editorial/analytics?category=stage5"
    )
    assert len(aggregate.data["results"]) == 1
    assert str(aggregate.data["categories"][0]["reach_percent"]) == "75.0"
    assert (
        call(client, settings, "editor-1", "get", "/api/v1/editorial/analytics.csv").status_code
        == 200
    )
    acknowledged = call(
        client,
        settings,
        "editor-1",
        "get",
        f"/api/v1/editorial/publications/{publication.pk}/acknowledgements?status=acknowledged",
    )
    pending = call(
        client,
        settings,
        "editor-1",
        "get",
        f"/api/v1/editorial/publications/{publication.pk}/acknowledgements?status=pending",
    )
    assert (len(acknowledged.data), len(pending.data)) == (2, 2)
    assert (
        call(
            client,
            settings,
            "editor-1",
            "get",
            f"/api/v1/editorial/publications/{publication.pk}/acknowledgements?status=bad",
        ).status_code
        == 400
    )
    csv_response = call(
        client,
        settings,
        "editor-1",
        "get",
        f"/api/v1/editorial/publications/{publication.pk}/acknowledgements.csv?status=pending",
    )
    assert csv_response.status_code == 200 and b"portal_id" in csv_response.content
    assert safe_csv_cell("=cmd") == "'=cmd"
    assert "'@name" in csv_text(["name"], [["@name"]])

    publication.acknowledgement_required = False
    publication.save(update_fields=["acknowledgement_required"])
    with pytest.raises(ValidationError):
        acknowledge(publication, User.objects.get(portal_id="admin-1"))
    publication.acknowledgement_required = True
    publication.save(update_fields=["acknowledgement_required"])
    outsider = User(portal_id="outsider", full_name="Outsider")
    outsider.set_unusable_password()
    outsider.save()
    with pytest.raises(PermissionDenied):
        acknowledge(publication, outsider)


@pytest.mark.django_db
def test_recipient_resolver_matches_visibility_for_every_audience_type(stage5):
    _client, publication, _asset = stage5
    users = list(User.objects.filter(is_active=True).select_related("org_unit"))
    cases = [
        {"kind": AudienceRule.Kind.ALL},
        {"kind": AudienceRule.Kind.EMPLOYEE, "employee": users[0]},
        {
            "kind": AudienceRule.Kind.ORG_UNIT,
            "org_unit": OrgUnit.objects.get(external_id="communications"),
        },
        {
            "kind": AudienceRule.Kind.ORG_UNIT,
            "org_unit": OrgUnit.objects.get(external_id="company"),
            "include_descendants": True,
        },
        {"kind": AudienceRule.Kind.MODULE_ROLE, "module_role": "author"},
        {
            "kind": AudienceRule.Kind.POSITION_GROUP,
            "position_group_external_id": "specialists",
            "position_group_name": "Специалисты",
        },
    ]
    for rule in cases:
        publication.audience_rules.all().delete()
        AudienceRule.objects.create(publication=publication, **rule)
        expected = {
            user.portal_id
            for user in users
            if Publication.objects.visible_to(user).filter(pk=publication.pk).exists()
        }
        assert {user.portal_id for user in resolve_recipient_users(publication)} == expected


@pytest.mark.django_db
def test_service_validation_branches_and_model_strings(stage5):
    _client, publication, asset = stage5
    employee = User.objects.get(portal_id="employee-1")
    editor = User.objects.get(portal_id="editor-1")
    other = Publication.objects.create(
        title="Other",
        slug="other-stage5",
        summary="Other",
        body={"type": "doc", "content": []},
        category=publication.category,
        author=editor,
        status=Publication.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    AudienceRule.objects.create(publication=other, kind=AudienceRule.Kind.ALL)
    foreign = Comment.objects.create(publication=other, author=editor, body="Foreign")
    with pytest.raises(Http404):
        create_comment(
            publication=publication, author=employee, body="Reply", reply_to_id=foreign.pk
        )
    comment = create_comment(publication=publication, author=employee, body="Normal")
    with pytest.raises(PermissionDenied):
        update_comment(publication=publication, comment_id=comment.pk, actor=editor, body="No")
    comment.status = Comment.Status.HIDDEN
    comment.save(update_fields=["status"])
    with pytest.raises(ValidationError):
        update_comment(publication=publication, comment_id=comment.pk, actor=employee, body="No")
    with pytest.raises(ValidationError):
        delete_comment(publication=publication, comment_id=comment.pk, actor=employee)
    with pytest.raises(ValidationError):
        moderate_comment(comment=comment, actor=editor, action="bad")
    moderate_comment(comment=comment, actor=editor, action="restore")
    with pytest.raises(ValidationError):
        moderate_comment(comment=comment, actor=editor, action="restore")
    publication.reactions_enabled = False
    publication.save(update_fields=["reactions_enabled"])
    with pytest.raises(PermissionDenied):
        put_reaction(publication=publication, user=employee, reaction_type="LIKE")
    publication.reactions_enabled = True
    publication.save(update_fields=["reactions_enabled"])
    with pytest.raises(ValidationError):
        put_reaction(publication=publication, user=employee, reaction_type="THANKS")
    engagement = EngagementSettings.load()
    engagement.enabled_reaction_types = ["LIKE", "THANKS"]
    engagement.save(update_fields=["enabled_reaction_types"])
    reaction, _ = put_reaction(publication=publication, user=employee, reaction_type="LIKE")
    assert delete_reaction(publication=publication, user=employee, reaction_type="THANKS") is False
    assert str(reaction).endswith("LIKE")
    word = StopWord.objects.create(value="word", normalized_value="word")
    attachment = CommentAttachment.objects.create(comment=comment, asset=asset)
    mention = CommentMention.objects.create(comment=comment, mentioned_user=editor)
    flag = ModerationFlag.objects.create(comment=comment, matched_word="word")
    restriction = CommentRestriction.objects.create(user=employee, created_by=editor)
    assert all(
        str(item)
        for item in (word, attachment, mention, flag, restriction, EngagementSettings.load())
    )
