"""Deterministic Stage 5 acceptance against real PostgreSQL and Redis."""

import os
import sys
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django.setup()

from django.core.cache import cache  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.discussions.models import (  # noqa: E402
    Comment,
    CommentReport,
    CommentRestriction,
    EngagementSettings,
    Notification,
    Reaction,
)
from apps.discussions.services import (  # noqa: E402
    create_comment,
    moderate_comment,
    put_reaction,
    report_comment,
)
from apps.identity.models import User  # noqa: E402
from apps.publications.engagement import (  # noqa: E402
    acknowledge,
    csv_text,
    publication_metrics,
)
from apps.publications.models import (  # noqa: E402
    AudienceRule,
    AuditEvent,
    Category,
    Publication,
    PublicationRecipient,
    PublicationView,
)
from apps.publications.services import transition_publication  # noqa: E402

PREFIX = "[STAGE5-VERIFY]"


def users() -> tuple[User, User, User, User]:
    return (
        User.objects.get(portal_id="employee-1"),
        User.objects.get(portal_id="author-1"),
        User.objects.get(portal_id="editor-1"),
        User.objects.get(portal_id="admin-1"),
    )


def prepare() -> None:
    employee, author, editor, admin = users()
    settings_row = EngagementSettings.load()
    settings_row.enabled_reaction_types = ["LIKE", "INSIGHTFUL"]
    settings_row.save(update_fields=["enabled_reaction_types"])
    category, _ = Category.objects.get_or_create(
        slug="stage5-verifier", defaults={"name": "Stage 5 verifier"}
    )
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    publication = Publication.objects.create(
        title=f"{PREFIX} {timestamp}",
        slug=f"stage5-verify-{timestamp}",
        summary="Deterministic engagement acceptance",
        body={
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Stage 5 acceptance"}],
                }
            ],
        },
        category=category,
        author=editor,
        acknowledgement_required=True,
    )
    AudienceRule.objects.create(publication=publication, kind=AudienceRule.Kind.ALL)
    transition_publication(publication, action="publish", actor=editor)
    publication.refresh_from_db()
    root = create_comment(publication=publication, author=employee, body="Root comment")
    reply = create_comment(
        publication=publication,
        author=admin,
        body="Reply with mention",
        reply_to_id=root.pk,
        mentioned_users=[employee],
    )
    put_reaction(
        publication=publication,
        user=author,
        reaction_type=Reaction.Type.INSIGHTFUL,
    )
    put_reaction(
        publication=publication,
        comment=root,
        user=admin,
        reaction_type=Reaction.Type.LIKE,
    )
    report_comment(comment=reply, reporter=employee, reason="Acceptance report")
    moderate_comment(comment=reply, actor=editor, action="hide")
    moderate_comment(comment=reply, actor=editor, action="restore")
    CommentRestriction.objects.create(
        user=admin,
        created_by=editor,
        reason="Expired acceptance restriction",
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    for recipient in (employee, author):
        acknowledge(publication, recipient)
    now = timezone.now()
    for viewer in (employee, author, editor):
        PublicationView.objects.get_or_create(
            publication=publication,
            user=viewer,
            defaults={"first_viewed_at": now, "last_viewed_at": now},
        )
    cache.set("stage5:acceptance:prepared", str(publication.pk), timeout=300)
    print(f"publication_id={publication.pk}")
    print("stage5_prepare=PASS")


def verify() -> None:
    publication = (
        Publication.objects.filter(title__startswith=PREFIX)
        .select_related("category")
        .latest("created_at")
    )
    roots = Comment.objects.filter(publication=publication, thread_root__isnull=True)
    root = roots.get()
    reply = Comment.objects.get(publication=publication, thread_root=root)
    assert reply.reply_to == root and reply.status == Comment.Status.ACTIVE
    assert (
        Notification.objects.filter(comment=reply, recipient__portal_id="employee-1").count() == 1
    )
    assert Reaction.objects.filter(publication=publication).count() == 1
    assert Reaction.objects.filter(comment=root).count() == 1
    assert (
        CommentReport.objects.filter(comment=reply, status=CommentReport.Status.OPEN).count() == 1
    )
    recipient_ids = set(
        PublicationRecipient.objects.filter(publication=publication, is_current=True).values_list(
            "user_id", flat=True
        )
    )
    assert recipient_ids == set(User.objects.filter(is_active=True).values_list("pk", flat=True))
    recipient_count = len(recipient_ids)

    def percent(numerator: int) -> Decimal:
        return (Decimal(numerator) * 100 / Decimal(recipient_count)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

    metrics = publication_metrics(publication)
    assert metrics["recipients"] == recipient_count
    assert metrics["unique_views"] == 3
    assert metrics["reach_percent"] == percent(3)
    assert metrics["unique_engaged"] == 3
    assert metrics["engagement_percent"] == percent(3)
    assert metrics["acknowledgement_percent"] == percent(2)
    assert (
        AuditEvent.objects.filter(
            target_type=AuditEvent.TargetType.COMMENT, target_id=str(reply.pk)
        ).count()
        == 2
    )
    assert "'=formula" in csv_text(["value"], [["=formula"]])
    assert cache.get("stage5:acceptance:prepared") is None or cache.get(
        "stage5:acceptance:prepared"
    ) == str(publication.pk)
    print(f"recipients={metrics['recipients']}")
    print(f"reach_percent={metrics['reach_percent']}")
    print(f"engagement_percent={metrics['engagement_percent']}")
    print(f"acknowledgement_percent={metrics['acknowledgement_percent']}")
    print("stage5_verify=PASS")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if mode == "prepare":
        prepare()
    elif mode == "verify":
        verify()
    else:
        raise SystemExit("Use prepare or verify")
