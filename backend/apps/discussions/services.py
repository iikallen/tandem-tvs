import unicodedata
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.identity.models import User
from apps.publications.models import AuditEvent, MediaAsset, MediaUsage, Publication
from apps.publications.services import record_audit_event

from .events import publish_after_commit
from .models import (
    Comment,
    CommentAttachment,
    CommentMention,
    CommentReport,
    CommentRestriction,
    EngagementSettings,
    ModerationFlag,
    Reaction,
    StopWord,
)


def normalize_comment_body(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        character
        for character in normalized
        if character in "\n\t" or unicodedata.category(character) != "Cc"
    ).strip()
    if not normalized:
        raise ValidationError("Comment body cannot be blank.")
    if len(normalized) > 5_000:
        raise ValidationError("Comment body cannot exceed 5000 characters.")
    return normalized


def normalize_stop_word(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    if not normalized or len(normalized) > 100:
        raise ValidationError("Stop word must contain 1 to 100 characters.")
    return normalized


def _is_restricted(user: User) -> bool:
    now = timezone.now()
    return (
        CommentRestriction.objects.filter(user=user, revoked_at__isnull=True)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .exists()
    )


def _reply_context(publication: Publication, reply_to_id: object | None):
    if reply_to_id is None:
        return None, None
    parent = get_object_or_404(Comment, pk=reply_to_id, publication=publication)
    root = parent.thread_root or parent
    if root.publication.pk != publication.pk:
        raise ValidationError("Reply target belongs to another publication.")
    return root, parent


def _validate_assets(publication: Publication, assets: list[MediaAsset], author: User) -> None:
    settings_row = EngagementSettings.load()
    if assets and not publication.category.comment_attachments_enabled:
        raise ValidationError("Comment attachments are disabled for this category.")
    if len(assets) > settings_row.max_comment_attachments:
        raise ValidationError("Too many comment attachments.")
    if len({asset.pk for asset in assets}) != len(assets):
        raise ValidationError("Comment attachments must be unique.")
    asset_ids = [asset.pk for asset in assets]
    if MediaAsset.objects.filter(pk__in=asset_ids, uploader=author).count() != len(assets):
        raise ValidationError("Comment attachments must be uploaded by the comment author.")
    if (
        MediaUsage.objects.filter(asset_id__in=asset_ids).exists()
        or CommentAttachment.objects.filter(asset_id__in=asset_ids).exists()
    ):
        raise ValidationError("Comment attachments cannot reuse media already in use.")
    if any(
        asset.status != MediaAsset.Status.READY
        or asset.size > settings_row.max_comment_attachment_bytes
        for asset in assets
    ):
        raise ValidationError("Comment attachment is not ready or exceeds the size limit.")


@transaction.atomic
def create_comment(
    *,
    publication: Publication,
    author: User,
    body: str,
    reply_to_id: object | None = None,
    mentioned_users: list[User] | None = None,
    assets: list[MediaAsset] | None = None,
) -> Comment:
    publication = (
        Publication.objects.select_for_update().select_related("category").get(pk=publication.pk)
    )
    if not publication.comments_enabled:
        raise PermissionDenied("Discussion is closed.")
    if _is_restricted(author):
        raise PermissionDenied("Commenting is restricted for this user.")
    root, parent = _reply_context(publication, reply_to_id)
    users = list({user.pk: user for user in (mentioned_users or [])}.values())
    for user in users:
        if not Publication.objects.visible_to(user).filter(pk=publication.pk).exists():
            raise ValidationError("Mentioned employee cannot access this publication.")
    attachments = assets or []
    _validate_assets(publication, attachments, author)
    comment = Comment.objects.create(
        publication=publication,
        author=author,
        body=normalize_comment_body(body),
        thread_root=root,
        reply_to=parent,
    )
    CommentMention.objects.bulk_create(
        [CommentMention(comment=comment, mentioned_user=user) for user in users]
    )
    CommentAttachment.objects.bulk_create(
        [
            CommentAttachment(comment=comment, asset=asset, sort_order=index)
            for index, asset in enumerate(attachments)
        ]
    )
    from apps.notifications.models import Notification
    from apps.notifications.services import enqueue_fanout

    recipients = {user.pk: Notification.Type.COMMENT_MENTION for user in users}
    if parent is not None and parent.author.pk != author.pk:
        recipients.setdefault(parent.author.pk, Notification.Type.COMMENT_REPLY)
    recipients.pop(author.pk, None)
    for kind in set(recipients.values()):
        enqueue_fanout(
            event_key=f"comment:{comment.pk}:{kind}",
            event_type=kind,
            source_id=comment.pk,
            payload={
                "actor_id": author.pk,
                "publication_id": str(publication.pk),
                "recipient_ids": [
                    user_id for user_id, value in recipients.items() if value == kind
                ],
                "source_type": "COMMENT",
            },
        )
    folded = unicodedata.normalize("NFKC", comment.body).casefold()
    flags = [
        ModerationFlag(comment=comment, matched_word=word.value)
        for word in StopWord.objects.filter(is_active=True)
        if word.normalized_value in folded
    ]
    ModerationFlag.objects.bulk_create(flags, ignore_conflicts=True)
    publish_after_commit(
        event_type="comment.created", publication_id=publication.pk, resource_id=comment.pk
    )
    return comment


def own_comment_or_denied(*, publication: Publication, comment_id: object, actor: User) -> Comment:
    comment = get_object_or_404(
        Comment.objects.select_for_update(), pk=comment_id, publication=publication
    )
    if comment.author.pk != actor.pk:
        raise PermissionDenied("Only the comment author may change it.")
    return comment


def _inside_window(comment: Comment, minutes: int) -> bool:
    return timezone.now() < comment.created_at + timedelta(minutes=minutes)


@transaction.atomic
def update_comment(
    *, publication: Publication, comment_id: object, actor: User, body: str
) -> Comment:
    comment = own_comment_or_denied(publication=publication, comment_id=comment_id, actor=actor)
    if comment.status != Comment.Status.ACTIVE:
        raise ValidationError("Only active comments can be edited.")
    if not _inside_window(comment, EngagementSettings.load().comment_edit_window_minutes):
        raise PermissionDenied("The comment edit window has expired.")
    comment.body = normalize_comment_body(body)
    comment.edited_at = timezone.now()
    comment.save(update_fields=["body", "edited_at", "updated_at"])
    publish_after_commit(
        event_type="comment.updated", publication_id=publication.pk, resource_id=comment.pk
    )
    return comment


@transaction.atomic
def delete_comment(*, publication: Publication, comment_id: object, actor: User) -> Comment:
    comment = own_comment_or_denied(publication=publication, comment_id=comment_id, actor=actor)
    if comment.status == Comment.Status.DELETED:
        return comment
    if comment.status != Comment.Status.ACTIVE:
        raise ValidationError("Only active comments can be deleted by their author.")
    if not _inside_window(comment, EngagementSettings.load().comment_delete_window_minutes):
        raise PermissionDenied("The comment delete window has expired.")
    comment.status = Comment.Status.DELETED
    comment.body = ""
    comment.deleted_at = timezone.now()
    comment.save(update_fields=["status", "body", "deleted_at", "updated_at"])
    publish_after_commit(
        event_type="comment.deleted", publication_id=publication.pk, resource_id=comment.pk
    )
    return comment


def _validate_reaction(publication: Publication, reaction_type: str) -> None:
    if not publication.reactions_enabled:
        raise PermissionDenied("Reactions are disabled for this publication.")
    if (
        reaction_type not in Reaction.Type.values
        or reaction_type not in EngagementSettings.load().enabled_reaction_types
    ):
        raise ValidationError("Reaction type is disabled.")


@transaction.atomic
def put_reaction(
    *, publication: Publication, user: User, reaction_type: str, comment: Comment | None = None
) -> tuple[Reaction, bool]:
    _validate_reaction(publication, reaction_type)
    if comment is not None and comment.publication.pk != publication.pk:
        raise ValidationError("Reaction target belongs to another publication.")
    lookup = (
        {"comment": comment, "user": user}
        if comment
        else {"publication": publication, "user": user}
    )
    try:
        with transaction.atomic():
            reaction, created = Reaction.objects.select_for_update().get_or_create(
                **lookup, defaults={"reaction_type": reaction_type}
            )
    except IntegrityError:
        reaction = Reaction.objects.select_for_update().get(**lookup)
        created = False
    changed = reaction.reaction_type != reaction_type
    if changed:
        reaction.reaction_type = reaction_type
        reaction.save(update_fields=["reaction_type", "updated_at"])
    if created or changed:
        publish_after_commit(
            event_type="reaction.changed", publication_id=publication.pk, resource_id=reaction.pk
        )
    return reaction, created


@transaction.atomic
def delete_reaction(
    *, publication: Publication, user: User, reaction_type: str, comment: Comment | None = None
) -> bool:
    _validate_reaction(publication, reaction_type)
    lookup = (
        {"comment": comment, "user": user}
        if comment
        else {"publication": publication, "user": user}
    )
    deleted, _ = Reaction.objects.filter(**lookup, reaction_type=reaction_type).delete()
    if deleted:
        publish_after_commit(
            event_type="reaction.changed",
            publication_id=publication.pk,
            resource_id=comment.pk if comment else publication.pk,
        )
    return bool(deleted)


@transaction.atomic
def report_comment(
    *, comment: Comment, reporter: User, reason: str = ""
) -> tuple[CommentReport, bool]:
    return CommentReport.objects.get_or_create(
        comment=comment, reporter=reporter, defaults={"reason": reason.strip()[:500]}
    )


@transaction.atomic
def moderate_comment(*, comment: Comment, actor: User, action: str) -> Comment:
    transitions = {
        "hide": ({Comment.Status.ACTIVE}, Comment.Status.HIDDEN, AuditEvent.Type.COMMENT_HIDDEN),
        "restore": (
            {Comment.Status.HIDDEN},
            Comment.Status.ACTIVE,
            AuditEvent.Type.COMMENT_RESTORED,
        ),
        "remove": (
            {Comment.Status.ACTIVE, Comment.Status.HIDDEN},
            Comment.Status.REMOVED,
            AuditEvent.Type.COMMENT_REMOVED,
        ),
    }
    if action not in transitions:
        raise ValidationError("Unknown moderation action.")
    comment = Comment.objects.select_for_update().get(pk=comment.pk)
    allowed, target, event_type = transitions[action]
    if comment.status not in allowed:
        raise ValidationError("Moderation transition is not allowed.")
    previous = {"status": comment.status, "body": comment.body}
    comment.status = target
    comment.deleted_at = timezone.now() if target == Comment.Status.REMOVED else None
    comment.save(update_fields=["status", "deleted_at", "updated_at"])
    record_audit_event(
        publication=comment.publication,
        actor=actor,
        event_type=event_type,
        target_type=AuditEvent.TargetType.COMMENT,
        target_id=comment.pk,
        previous_state=previous,
        new_state={"status": target},
    )
    publish_after_commit(
        event_type="comment.moderated",
        publication_id=comment.publication.pk,
        resource_id=comment.pk,
    )
    return comment
