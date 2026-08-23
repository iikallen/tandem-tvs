import unicodedata

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.identity.models import User
from apps.publications.models import Publication

from .events import publish_after_commit
from .models import Comment, Reaction


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


@transaction.atomic
def create_comment(*, publication: Publication, author: User, body: str) -> Comment:
    comment = Comment.objects.create(
        publication=publication, author=author, body=normalize_comment_body(body)
    )
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


@transaction.atomic
def update_comment(
    *, publication: Publication, comment_id: object, actor: User, body: str
) -> Comment:
    comment = own_comment_or_denied(publication=publication, comment_id=comment_id, actor=actor)
    if comment.status != Comment.Status.ACTIVE:
        raise ValidationError("Deleted comments cannot be edited.")
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
    comment.status = Comment.Status.DELETED
    comment.body = ""
    comment.deleted_at = timezone.now()
    comment.save(update_fields=["status", "body", "deleted_at", "updated_at"])
    publish_after_commit(
        event_type="comment.deleted", publication_id=publication.pk, resource_id=comment.pk
    )
    return comment


@transaction.atomic
def put_reaction(
    *, publication: Publication, user: User, reaction_type: str
) -> tuple[Reaction, bool]:
    reaction, created = Reaction.objects.get_or_create(
        publication=publication, user=user, reaction_type=reaction_type
    )
    if created:
        publish_after_commit(
            event_type="reactions.changed",
            publication_id=publication.pk,
            resource_id=reaction.pk,
        )
    return reaction, created


@transaction.atomic
def delete_reaction(*, publication: Publication, user: User, reaction_type: str) -> bool:
    deleted, _ = Reaction.objects.filter(
        publication=publication, user=user, reaction_type=reaction_type
    ).delete()
    if deleted:
        publish_after_commit(
            event_type="reactions.changed", publication_id=publication.pk, resource_id=None
        )
    return bool(deleted)
