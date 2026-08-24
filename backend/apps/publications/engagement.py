import csv
import io
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.discussions.models import Comment, Reaction
from apps.identity.models import User
from apps.identity.permissions import legacy_news_roles
from apps.organization.models import OrgUnit

from .models import (
    Acknowledgement,
    AudienceRule,
    AuditEvent,
    Publication,
    PublicationRecipient,
    PublicationView,
)
from .services import record_audit_event


def resolve_recipient_users(publication: Publication):
    """Resolve the same audience rules as ``visible_to`` without per-user queries."""
    now = timezone.now()
    if (
        publication.status != Publication.Status.PUBLISHED
        or publication.published_at is None
        or publication.published_at > now
        or (publication.expires_at is not None and publication.expires_at <= now)
    ):
        return []

    rules = list(publication.audience_rules.select_related("org_unit", "employee"))
    if any(rule.kind == AudienceRule.Kind.ALL for rule in rules):
        return list(User.objects.filter(is_active=True).select_related("org_unit"))

    employee_ids = {
        rule.employee.portal_id
        for rule in rules
        if rule.kind == AudienceRule.Kind.EMPLOYEE and rule.employee is not None
    }
    roles = {rule.module_role for rule in rules if rule.kind == AudienceRule.Kind.MODULE_ROLE}
    position_groups = {
        rule.position_group_external_id
        for rule in rules
        if rule.kind == AudienceRule.Kind.POSITION_GROUP
    }
    org_rules = {
        rule.org_unit.external_id: rule.include_descendants
        for rule in rules
        if rule.kind == AudienceRule.Kind.ORG_UNIT
        and rule.org_unit is not None
        and rule.org_unit.is_active
    }
    org_units = {row.pk: row for row in OrgUnit.objects.all()}

    def matches(user: User) -> bool:
        if user.portal_id in employee_ids:
            return True
        if roles.intersection(legacy_news_roles(user)):
            return True
        if user.position_group_external_id in position_groups:
            return True
        current = user.org_unit
        if current is None or not current.is_active:
            return False
        seen: set[str] = set()
        while current is not None and current.external_id not in seen:
            seen.add(current.external_id)
            if current.is_active and (
                current.pk == user.org_unit.pk or org_rules.get(current.external_id, False)
            ):
                if current.external_id in org_rules:
                    return True
            current = org_units.get(cast(Any, current).parent_id)
        return False

    return [
        user
        for user in User.objects.filter(is_active=True)
        .select_related("org_unit")
        .prefetch_related("access_grants")
        if matches(user)
    ]


@transaction.atomic
def refresh_recipient_snapshot(publication: Publication) -> list[PublicationRecipient]:
    publication = Publication.objects.select_for_update().get(pk=publication.pk)
    users = resolve_recipient_users(publication)
    current_ids = {user.pk for user in users}
    PublicationRecipient.objects.filter(publication=publication).exclude(
        user_id__in=current_ids
    ).update(is_current=False)
    rows = []
    for user in users:
        org = user.org_unit
        row, _ = PublicationRecipient.objects.update_or_create(
            publication=publication,
            user=user,
            defaults={
                "portal_id": user.portal_id or "",
                "full_name": user.full_name,
                "email": user.email,
                "org_unit_external_id": org.external_id if org else "",
                "org_unit_name": org.name if org else "",
                "is_current": True,
            },
        )
        rows.append(row)
    return rows


@transaction.atomic
def acknowledge(publication: Publication, user: User) -> tuple[Acknowledgement, bool]:
    if not publication.acknowledgement_required:
        raise ValidationError("Acknowledgement is not required for this publication.")
    recipient = (
        PublicationRecipient.objects.select_for_update()
        .filter(publication=publication, user=user, is_current=True)
        .first()
    )
    if recipient is None:
        raise PermissionDenied("Only a current publication recipient can acknowledge it.")
    row, created = Acknowledgement.objects.get_or_create(
        publication=publication, recipient=recipient, user=user
    )
    if created:
        record_audit_event(
            publication=publication,
            actor=user,
            event_type=AuditEvent.Type.ACKNOWLEDGED,
            target_type=AuditEvent.TargetType.ACKNOWLEDGEMENT,
            target_id=row.pk,
            new_state={"portal_id": recipient.portal_id},
        )
    return row, created


def _percent(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.0")
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


def _metrics_from_sets(
    publication: Publication,
    recipients: list[PublicationRecipient],
    viewed_ids: set[object],
    comment_count: int,
    comment_user_ids: set[object],
    reaction_count: int,
    reaction_user_ids: set[object],
    acknowledged_ids: set[object],
) -> dict[str, object]:
    recipient_count = len(recipients)
    user_ids = {cast(Any, row).user_id for row in recipients}
    viewed_ids &= user_ids
    comment_user_ids &= user_ids
    reaction_user_ids &= user_ids
    acknowledged_ids &= user_ids
    departments = []
    names = sorted({row.org_unit_name or "—" for row in recipients})
    for name in names:
        department_ids = {
            cast(Any, row).user_id for row in recipients if (row.org_unit_name or "—") == name
        }
        departments.append(
            {
                "name": name,
                "recipients": len(department_ids),
                "unique_views": len(viewed_ids & department_ids),
                "reach_percent": _percent(len(viewed_ids & department_ids), len(department_ids)),
                "acknowledged": len(acknowledged_ids & department_ids),
            }
        )
    engaged_ids = comment_user_ids | reaction_user_ids
    return {
        "publication_id": str(publication.pk),
        "title": publication.title,
        "category": publication.category.name,
        "recipients": recipient_count,
        "views": len(viewed_ids),
        "unique_views": len(viewed_ids),
        "reach_percent": _percent(len(viewed_ids), recipient_count),
        "comments": comment_count,
        "reactions": reaction_count,
        "unique_engaged": len(engaged_ids),
        "engagement_percent": _percent(len(engaged_ids), recipient_count),
        "acknowledged": len(acknowledged_ids),
        "pending": recipient_count - len(acknowledged_ids),
        "acknowledgement_percent": (
            _percent(len(acknowledged_ids), recipient_count)
            if publication.acknowledgement_required
            else None
        ),
        "departments": departments,
    }


def publication_metrics(publication: Publication) -> dict[str, object]:
    recipients = list(PublicationRecipient.objects.filter(publication=publication, is_current=True))
    user_ids = {cast(Any, row).user_id for row in recipients}
    viewed_ids = set(
        PublicationView.objects.filter(publication=publication, user_id__in=user_ids).values_list(
            "user_id", flat=True
        )
    )
    comments = Comment.objects.filter(publication=publication).exclude(
        status=Comment.Status.REMOVED
    )
    comment_user_ids = set(
        comments.filter(author_id__in=user_ids).values_list("author_id", flat=True)
    )
    publication_reactions = Reaction.objects.filter(publication=publication)
    comment_reactions = Reaction.objects.filter(comment__publication=publication).exclude(
        comment__status=Comment.Status.REMOVED
    )
    reaction_user_ids = set(
        publication_reactions.filter(user_id__in=user_ids).values_list("user_id", flat=True)
    ) | set(comment_reactions.filter(user_id__in=user_ids).values_list("user_id", flat=True))
    acknowledged_ids = set(
        Acknowledgement.objects.filter(
            publication=publication, recipient__is_current=True
        ).values_list("user_id", flat=True)
    )
    return _metrics_from_sets(
        publication,
        recipients,
        viewed_ids,
        comments.count(),
        comment_user_ids,
        publication_reactions.count() + comment_reactions.count(),
        reaction_user_ids,
        acknowledged_ids,
    )


def publication_metrics_bulk(publications: list[Publication]) -> list[dict[str, object]]:
    publication_ids = [publication.pk for publication in publications]
    recipients: dict[object, list[PublicationRecipient]] = defaultdict(list)
    views: dict[object, set[object]] = defaultdict(set)
    comment_counts: dict[object, int] = defaultdict(int)
    comment_users: dict[object, set[object]] = defaultdict(set)
    reaction_counts: dict[object, int] = defaultdict(int)
    reaction_users: dict[object, set[object]] = defaultdict(set)
    acknowledgements: dict[object, set[object]] = defaultdict(set)

    for row in PublicationRecipient.objects.filter(
        publication_id__in=publication_ids, is_current=True
    ):
        recipients[cast(Any, row).publication_id].append(row)
    for publication_id, user_id in PublicationView.objects.filter(
        publication_id__in=publication_ids
    ).values_list("publication_id", "user_id"):
        views[publication_id].add(user_id)
    for publication_id, user_id in (
        Comment.objects.filter(publication_id__in=publication_ids)
        .exclude(status=Comment.Status.REMOVED)
        .values_list("publication_id", "author_id")
    ):
        comment_counts[publication_id] += 1
        comment_users[publication_id].add(user_id)
    for publication_id, user_id in Reaction.objects.filter(
        publication_id__in=publication_ids
    ).values_list("publication_id", "user_id"):
        reaction_counts[publication_id] += 1
        reaction_users[publication_id].add(user_id)
    for publication_id, user_id in (
        Reaction.objects.filter(comment__publication_id__in=publication_ids)
        .exclude(comment__status=Comment.Status.REMOVED)
        .values_list("comment__publication_id", "user_id")
    ):
        reaction_counts[publication_id] += 1
        reaction_users[publication_id].add(user_id)
    for publication_id, user_id in Acknowledgement.objects.filter(
        publication_id__in=publication_ids, recipient__is_current=True
    ).values_list("publication_id", "user_id"):
        acknowledgements[publication_id].add(user_id)

    return [
        _metrics_from_sets(
            publication,
            recipients[publication.pk],
            views[publication.pk],
            comment_counts[publication.pk],
            comment_users[publication.pk],
            reaction_counts[publication.pk],
            reaction_users[publication.pk],
            acknowledgements[publication.pk],
        )
        for publication in publications
    ]


def safe_csv_cell(value: object) -> str:
    text = str(value if value is not None else "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


def csv_text(headers: list[str], rows: list[list[object]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows([[safe_csv_cell(cell) for cell in row] for row in rows])
    return stream.getvalue()


def category_metrics(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, int]] = {}
    for row in rows:
        category = str(row["category"])
        current = grouped.setdefault(
            category,
            {"publications": 0, "recipients": 0, "unique_views": 0, "comments": 0, "reactions": 0},
        )
        current["publications"] += 1
        for key in ("recipients", "unique_views", "comments", "reactions"):
            current[key] += cast(int, row[key])
    return [
        {
            "category": name,
            **values,
            "reach_percent": _percent(values["unique_views"], values["recipients"]),
        }
        for name, values in sorted(grouped.items())
    ]
