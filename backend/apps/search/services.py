import base64
import binascii

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramSimilarity
from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Greatest

from apps.discussions.models import Comment
from apps.identity.models import User
from apps.messenger.models import ConversationMembership, Message
from apps.publications.models import MediaAsset, Publication


def _vectors(fields: list[tuple[str, str]]):
    russian = SearchVector(fields[0][0], weight=fields[0][1], config="russian")
    kazakh = SearchVector(fields[0][0], weight=fields[0][1], config="tandem_kazakh")
    for field, weight in fields[1:]:
        russian += SearchVector(field, weight=weight, config="russian")
        kazakh += SearchVector(field, weight=weight, config="tandem_kazakh")
    return russian, kazakh


def _ranked(queryset, fields: list[tuple[str, str]], query: str):
    russian, kazakh = _vectors(fields)
    query_ru = SearchQuery(query, config="russian", search_type="websearch")
    query_kk = SearchQuery(query, config="tandem_kazakh", search_type="websearch")
    return (
        queryset.annotate(search_rank=SearchRank(russian, query_ru) + SearchRank(kazakh, query_kk))
        .filter(search_rank__gt=0)
        .order_by("-search_rank", "-id")
    )


def authorized_messages(user: User):
    active = ConversationMembership.objects.filter(
        conversation_id=OuterRef("conversation_id"), user=user, left_at__isnull=True
    )
    interval = ConversationMembership.objects.filter(
        conversation_id=OuterRef("conversation_id"),
        user=user,
        joined_sequence__lt=OuterRef("sequence"),
    ).filter(Q(left_sequence__isnull=True) | Q(left_sequence__gte=OuterRef("sequence")))
    return Message.objects.annotate(
        has_current_access=Exists(active), in_visible_interval=Exists(interval)
    ).filter(
        has_current_access=True,
        in_visible_interval=True,
        deleted_at__isnull=True,
    )


def authorized_sections(user: User, query: str):
    publications = _ranked(
        Publication.objects.visible_to(user),
        [("title", "A"), ("summary", "B"), ("body_text", "C")],
        query,
    ).select_related("author", "category")
    comments = _ranked(
        Comment.objects.filter(
            status=Comment.Status.ACTIVE,
            publication_id__in=Publication.objects.visible_to(user).values("pk"),
        ),
        [("body", "A")],
        query,
    ).select_related("author", "publication")
    messages = _ranked(authorized_messages(user), [("body", "A")], query).select_related(
        "author", "conversation"
    )

    visible_publications = Publication.objects.visible_to(user).values("pk")
    visible_comments = Comment.objects.filter(
        status=Comment.Status.ACTIVE, publication_id__in=visible_publications
    ).values("pk")
    visible_messages = authorized_messages(user).values("pk")
    files = _ranked(
        MediaAsset.objects.filter(status=MediaAsset.Status.READY)
        .filter(
            Q(usages__publication_id__in=visible_publications)
            | Q(comment_attachments__comment_id__in=visible_comments)
            | Q(messenger_attachments__message_id__in=visible_messages)
        )
        .distinct(),
        [("original_name", "A")],
        query,
    )
    employee_ru, employee_kk = _vectors([("full_name", "A"), ("job_title", "B")])
    employees = (
        User.objects.filter(is_active=True)
        .annotate(
            fts_rank=SearchRank(
                employee_ru,
                SearchQuery(query, config="russian", search_type="websearch"),
            )
            + SearchRank(
                employee_kk,
                SearchQuery(query, config="tandem_kazakh", search_type="websearch"),
            ),
            trigram_rank=Greatest(
                TrigramSimilarity("full_name", query),
                TrigramSimilarity("job_title", query),
            ),
            search_rank=Greatest(
                "fts_rank",
                "trigram_rank",
            ),
        )
        .filter(
            Q(search_rank__gt=0.08) | Q(full_name__icontains=query) | Q(job_title__icontains=query)
        )
        .select_related("org_unit")
        .order_by("-search_rank", "full_name", "id")
    )
    return {
        "publications": publications,
        "comments": comments,
        "messages": messages,
        "files": files,
        "employees": employees,
    }


def plain_snippet(value: str, limit: int = 240) -> str:
    return " ".join(value.split())[:limit]


def decode_cursor(value: str | None) -> int:
    if not value:
        return 0
    try:
        padded = value + "=" * (-len(value) % 4)
        offset = int(base64.urlsafe_b64decode(padded).decode("ascii"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ValueError("Invalid search cursor.") from None
    if not 0 <= offset <= 10_000:
        raise ValueError("Invalid search cursor.")
    return offset


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")


def serialize_result(scope: str, row) -> dict[str, object]:
    if scope == "publications":
        return {
            "id": str(row.pk),
            "title": row.title,
            "snippet": plain_snippet(row.summary or row.body_text),
            "url": f"/news/{row.pk}",
        }
    if scope == "comments":
        return {
            "id": str(row.pk),
            "title": row.publication.title,
            "snippet": plain_snippet(row.body),
            "author": row.author.full_name,
            "url": f"/news/{row.publication_id}?comment={row.pk}",
        }
    if scope == "messages":
        return {
            "id": str(row.pk),
            "title": row.conversation.title or row.author.full_name,
            "snippet": plain_snippet(row.body),
            "author": row.author.full_name,
            "url": f"/messages?conversation={row.conversation_id}&message={row.pk}",
        }
    if scope == "files":
        return {
            "id": str(row.pk),
            "title": row.original_name,
            "snippet": row.kind,
            "url": f"/api/v1/media/{row.pk}/content",
        }
    return {
        "id": row.pk,
        "title": row.full_name,
        "snippet": plain_snippet(row.job_title),
        "avatar_url": row.avatar_url,
        "org_unit": row.org_unit.name if row.org_unit else None,
        "url": f"/employees?employee={row.pk}",
    }
