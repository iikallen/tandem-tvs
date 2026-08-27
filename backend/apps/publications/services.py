import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any, TypedDict, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import APIException
from rest_framework.generics import get_object_or_404

from apps.identity.models import AccessGrant, User
from apps.identity.permissions import has_any_role
from apps.organization.models import OrgUnit

from .models import (
    MAX_PINNED,
    MODULE_ROLE_MAX_LENGTH,
    POSITION_GROUP_MAX_LENGTH,
    AudienceRule,
    AuditEvent,
    MediaAsset,
    MediaUsage,
    Publication,
    PublicationPin,
    PublicationVersion,
    PublicationView,
    Tag,
)

EDITABLE_BY_AUTHOR = {Publication.Status.DRAFT, Publication.Status.UNPUBLISHED}
EDITABLE_BY_EDITOR = {
    Publication.Status.DRAFT,
    Publication.Status.IN_REVIEW,
    Publication.Status.SCHEDULED,
    Publication.Status.PUBLISHED,
    Publication.Status.UNPUBLISHED,
}
AUTOSAVE_VERSION_WINDOW = timedelta(minutes=1)


class StaleRevisionError(APIException):
    status_code = 409
    default_code = "stale_revision"

    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("Publication changed in another session.", code=self.default_code)


class PositionGroupPayload(TypedDict):
    external_id: str
    name: str


class AudiencePayload(TypedDict):
    everyone: bool
    org_units: list[str]
    org_unit_subtrees: list[str]
    employees: list[int]
    module_roles: list[str]
    position_groups: list[PositionGroupPayload]


def is_editor(user: object) -> bool:
    return has_any_role(
        user,
        AccessGrant.Module.NEWS,
        {AccessGrant.Role.EDITOR, AccessGrant.Role.ADMIN},
    )


def can_edit_publication(user: User, publication: Publication) -> bool:
    if is_editor(user):
        return publication.status in EDITABLE_BY_EDITOR
    return publication.author.pk == user.pk and publication.status in EDITABLE_BY_AUTHOR


def visible_publication_or_404(user: User, publication_id: object) -> Publication:
    """The single authorization boundary for publication child resources."""
    return get_object_or_404(Publication.objects.visible_to(user), pk=publication_id)


@transaction.atomic
def replace_audience_rules(
    publication: Publication,
    *,
    everyone: bool = False,
    org_units: Iterable[OrgUnit] = (),
    org_unit_subtrees: Iterable[OrgUnit] = (),
    employees: Iterable[User] = (),
    module_roles: Iterable[str] = (),
    position_groups: Iterable[PositionGroupPayload] = (),
) -> list[AudienceRule]:
    publication = Publication.objects.select_for_update().get(pk=publication.pk)
    exact_units = {unit.external_id: unit for unit in org_units}
    subtree_units = {unit.external_id: unit for unit in org_unit_subtrees}
    users = {user.pk: user for user in employees}
    roles = {role.strip() for role in module_roles if role.strip()}
    groups = {
        group["external_id"].strip(): group["name"].strip()
        for group in position_groups
        if group["external_id"].strip() and group["name"].strip()
    }
    if everyone and (exact_units or subtree_units or users or roles or groups):
        raise ValidationError("ALL audience cannot be combined with narrower rules.")
    if any(not unit.is_active for unit in [*exact_units.values(), *subtree_units.values()]):
        raise ValidationError("Inactive organization units cannot be audience targets.")
    if any(not user.is_active for user in users.values()):
        raise ValidationError("Inactive employees cannot be audience targets.")
    if any(len(role) > MODULE_ROLE_MAX_LENGTH for role in roles):
        raise ValidationError("Module role is too long.")
    if any(len(group_id) > POSITION_GROUP_MAX_LENGTH for group_id in groups):
        raise ValidationError("Position group identifier is too long.")

    rules = (
        [AudienceRule(publication=publication, kind=AudienceRule.Kind.ALL)]
        if everyone
        else [
            *(
                AudienceRule(
                    publication=publication,
                    kind=AudienceRule.Kind.ORG_UNIT,
                    org_unit=unit,
                    include_descendants=False,
                )
                for unit in exact_units.values()
            ),
            *(
                AudienceRule(
                    publication=publication,
                    kind=AudienceRule.Kind.ORG_UNIT,
                    org_unit=unit,
                    include_descendants=True,
                )
                for unit in subtree_units.values()
                if unit.external_id not in exact_units
            ),
            *(
                AudienceRule(
                    publication=publication,
                    kind=AudienceRule.Kind.EMPLOYEE,
                    employee=user,
                )
                for user in users.values()
            ),
            *(
                AudienceRule(
                    publication=publication,
                    kind=AudienceRule.Kind.MODULE_ROLE,
                    module_role=role,
                )
                for role in sorted(roles)
            ),
            *(
                AudienceRule(
                    publication=publication,
                    kind=AudienceRule.Kind.POSITION_GROUP,
                    position_group_external_id=group_id,
                    position_group_name=name,
                )
                for group_id, name in sorted(groups.items())
            ),
        ]
    )
    AudienceRule.objects.filter(publication=publication).delete()
    return AudienceRule.objects.bulk_create(rules)


@transaction.atomic
def record_publication_view(
    publication: Publication,
    user: User,
    *,
    viewed_at: datetime | None = None,
) -> PublicationView:
    timestamp = viewed_at or timezone.now()
    view, created = PublicationView.objects.get_or_create(
        publication=publication,
        user=user,
        defaults={"first_viewed_at": timestamp, "last_viewed_at": timestamp},
    )
    if not created:
        view.last_viewed_at = timestamp
        view.save(update_fields=["last_viewed_at"])
    return view


def publication_snapshot(publication: Publication) -> dict[str, object]:
    return {
        "title": publication.title,
        "summary": publication.summary,
        "body": publication.body,
        "category": publication.category.slug,
        "tags": list(publication.tags.order_by("slug").values_list("slug", flat=True)),
        "cover": str(publication.cover.pk) if publication.cover else None,
        "status": publication.status,
        "published_at": _iso(publication.published_at),
        "scheduled_for": _iso(publication.scheduled_for),
        "expires_at": _iso(publication.expires_at),
        "unpublished_at": _iso(publication.unpublished_at),
        "archived_at": _iso(publication.archived_at),
        "edit_revision": publication.edit_revision,
        "comments_enabled": publication.comments_enabled,
        "reactions_enabled": publication.reactions_enabled,
        "acknowledgement_required": publication.acknowledgement_required,
        "audience": list(
            AudienceRule.objects.filter(publication=publication)
            .order_by("id")
            .values(
                "kind",
                "org_unit_id",
                "include_descendants",
                "employee_id",
                "module_role",
                "position_group_external_id",
                "position_group_name",
            )
        ),
        "media": [
            {"asset_id": str(asset_id), "purpose": purpose}
            for asset_id, purpose in MediaUsage.objects.filter(publication=publication)
            .order_by("purpose", "asset_id")
            .values_list("asset_id", "purpose")
        ],
    }


def record_audit_event(
    *,
    actor: User,
    event_type: str,
    target_type: str,
    target_id: object,
    previous_state: dict[str, object] | None = None,
    new_state: dict[str, object] | None = None,
    publication: Publication | None = None,
) -> AuditEvent:
    return AuditEvent.objects.create(
        actor=actor,
        event_type=event_type,
        target_type=target_type,
        target_id=str(target_id),
        previous_state=previous_state or {},
        new_state=new_state or {},
        publication=publication,
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _canonical_hash(snapshot: dict[str, object]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _changed_fields(previous: dict[str, object], current: dict[str, object]) -> list[str]:
    return sorted(key for key in current if previous.get(key) != current.get(key))


def create_version(
    publication: Publication,
    *,
    actor: User,
    reason: str,
    previous: dict[str, object] | None = None,
    coalesce_autosave: bool = False,
) -> PublicationVersion | None:
    if (
        coalesce_autosave
        and PublicationVersion.objects.filter(
            publication=publication,
            actor=actor,
            reason="autosave",
            created_at__gte=timezone.now() - AUTOSAVE_VERSION_WINDOW,
        ).exists()
    ):
        return None
    snapshot = publication_snapshot(publication)
    number = (
        PublicationVersion.objects.filter(publication=publication).aggregate(
            value=Max("version_number")
        )["value"]
        or 0
    ) + 1
    return PublicationVersion.objects.create(
        publication=publication,
        version_number=number,
        actor=actor,
        reason=reason,
        snapshot=snapshot,
        changed_fields=_changed_fields(previous or {}, snapshot),
        content_hash=_canonical_hash(snapshot),
    )


def _slug_for(title: str, publication_id: uuid.UUID) -> str:
    base = slugify(title, allow_unicode=True)[:240] or "publication"
    if not Publication.objects.filter(slug=base).exists():
        return base
    return f"{base[:246]}-{publication_id.hex[:8]}"


def _audience_targets(payload: AudiencePayload):
    unit_ids = set(payload["org_units"]) | set(payload["org_unit_subtrees"])
    employee_ids = set(payload["employees"])
    units = list(OrgUnit.objects.filter(external_id__in=unit_ids, is_active=True))
    users = list(User.objects.filter(pk__in=employee_ids, is_active=True))
    unit_map = {unit.external_id: unit for unit in units}
    if set(unit_map) != unit_ids:
        raise ValidationError("Unknown or inactive organization audience target.")
    if {user.pk for user in users} != employee_ids:
        raise ValidationError("Unknown or inactive employee audience target.")
    return unit_map, users


def set_publication_audience(publication: Publication, payload: AudiencePayload) -> None:
    units, users = _audience_targets(payload)
    replace_audience_rules(
        publication,
        everyone=payload["everyone"],
        org_units=[units[value] for value in payload["org_units"]],
        org_unit_subtrees=[units[value] for value in payload["org_unit_subtrees"]],
        employees=users,
        module_roles=payload["module_roles"],
        position_groups=payload["position_groups"],
    )


def _set_tags(publication: Publication, tags: Iterable[Tag]) -> None:
    tag_list = list(tags)
    if any(not tag.is_active for tag in tag_list):
        raise ValidationError("Inactive tags cannot be assigned.")
    publication.tags.set(tag_list)


def _set_media_usages(
    publication: Publication,
    *,
    cover: MediaAsset | None,
    body_assets: Iterable[MediaAsset],
    attachments: Iterable[MediaAsset],
) -> None:
    if cover is not None and cover.kind != MediaAsset.Kind.IMAGE:
        raise ValidationError("Cover must be an image.")
    publication.cover = cover
    publication.save(update_fields=["cover", "updated_at"])
    MediaUsage.objects.filter(publication=publication).delete()
    rows = []
    if cover is not None:
        rows.append(
            MediaUsage(asset=cover, publication=publication, purpose=MediaUsage.Purpose.COVER)
        )
    rows.extend(
        MediaUsage(asset=asset, publication=publication, purpose=MediaUsage.Purpose.BODY)
        for asset in {asset.id: asset for asset in body_assets}.values()
    )
    rows.extend(
        MediaUsage(
            asset=asset,
            publication=publication,
            purpose=MediaUsage.Purpose.ATTACHMENT,
        )
        for asset in {asset.id: asset for asset in attachments}.values()
    )
    MediaUsage.objects.bulk_create(rows, ignore_conflicts=True)
    MediaAsset.objects.filter(pk__in=[row.asset.pk for row in rows]).update(temporary_until=None)


@transaction.atomic
def create_publication(*, actor: User, data: dict[str, object]) -> Publication:
    audience = cast(AudiencePayload, data.pop("audience"))
    tags = cast(list[Tag], data.pop("tags", []))
    cover = cast(MediaAsset | None, data.pop("cover", None))
    body_assets = cast(list[MediaAsset], data.pop("body_assets", []))
    attachments = cast(list[MediaAsset], data.pop("attachments", []))
    publication_id = uuid.uuid4()
    publication = Publication(
        id=publication_id,
        author=actor,
        slug=_slug_for(str(data["title"]), publication_id),
        edit_revision=1,
        **data,
    )
    publication.full_clean()
    publication.save()
    _set_tags(publication, tags)
    set_publication_audience(publication, audience)
    _set_media_usages(publication, cover=cover, body_assets=body_assets, attachments=attachments)
    record_audit_event(
        publication=publication,
        actor=actor,
        event_type=AuditEvent.Type.CREATED,
        target_type=AuditEvent.TargetType.PUBLICATION,
        target_id=publication.pk,
        new_state=publication_snapshot(publication),
    )
    create_version(publication, actor=actor, reason="created")
    return publication


@transaction.atomic
def update_publication(
    publication: Publication,
    *,
    actor: User,
    data: dict[str, object],
    expected_revision: int,
    autosave: bool = False,
) -> Publication:
    publication = (
        Publication.objects.select_for_update().select_related("category").get(pk=publication.pk)
    )
    if publication.edit_revision != expected_revision:
        raise StaleRevisionError(publication.edit_revision)
    if not can_edit_publication(actor, publication):
        raise PermissionDenied("This publication cannot be edited by the current user.")
    previous = publication_snapshot(publication)
    audience = cast(AudiencePayload | None, data.pop("audience", None))
    tags = cast(list[Tag] | None, data.pop("tags", None))
    cover_marker = data.pop("cover", ...)
    body_assets = cast(list[MediaAsset] | None, data.pop("body_assets", None))
    attachments = cast(list[MediaAsset] | None, data.pop("attachments", None))
    for field, value in data.items():
        setattr(publication, field, value)
    publication.edit_revision += 1
    if autosave:
        publication.last_autosaved_at = timezone.now()
    publication.full_clean()
    publication.save()
    if audience is not None:
        set_publication_audience(publication, audience)
        if publication.status == Publication.Status.PUBLISHED:
            from .engagement import refresh_recipient_snapshot

            refresh_recipient_snapshot(publication)
    if tags is not None:
        _set_tags(publication, tags)
    if cover_marker is not ... or body_assets is not None or attachments is not None:
        current: dict[str, list[MediaAsset]] = {}
        for usage in publication.media_usages.select_related("asset").all():
            current.setdefault(usage.purpose, []).append(usage.asset)
        _set_media_usages(
            publication,
            cover=(
                cast(MediaAsset | None, cover_marker)
                if cover_marker is not ...
                else publication.cover
            ),
            body_assets=body_assets if body_assets is not None else current.get("BODY", []),
            attachments=(attachments if attachments is not None else current.get("ATTACHMENT", [])),
        )
    record_audit_event(
        publication=publication,
        actor=actor,
        event_type=AuditEvent.Type.UPDATED,
        target_type=AuditEvent.TargetType.PUBLICATION,
        target_id=publication.pk,
        previous_state=previous,
        new_state=publication_snapshot(publication),
    )
    if previous.get("comments_enabled") != publication.comments_enabled:
        record_audit_event(
            publication=publication,
            actor=actor,
            event_type=(
                AuditEvent.Type.DISCUSSION_OPENED
                if publication.comments_enabled
                else AuditEvent.Type.DISCUSSION_CLOSED
            ),
            target_type=AuditEvent.TargetType.PUBLICATION,
            target_id=publication.pk,
            previous_state={"comments_enabled": previous.get("comments_enabled")},
            new_state={"comments_enabled": publication.comments_enabled},
        )
    create_version(
        publication,
        actor=actor,
        reason="autosave" if autosave else "manual_save",
        previous=previous,
        coalesce_autosave=autosave,
    )
    return publication


TRANSITIONS: dict[str, dict[str, str]] = {
    "submit-review": {Publication.Status.DRAFT: Publication.Status.IN_REVIEW},
    "return-to-draft": {Publication.Status.IN_REVIEW: Publication.Status.DRAFT},
    "publish": {
        Publication.Status.DRAFT: Publication.Status.PUBLISHED,
        Publication.Status.IN_REVIEW: Publication.Status.PUBLISHED,
        Publication.Status.UNPUBLISHED: Publication.Status.PUBLISHED,
        Publication.Status.SCHEDULED: Publication.Status.PUBLISHED,
    },
    "schedule": {
        Publication.Status.DRAFT: Publication.Status.SCHEDULED,
        Publication.Status.IN_REVIEW: Publication.Status.SCHEDULED,
        Publication.Status.UNPUBLISHED: Publication.Status.SCHEDULED,
        Publication.Status.SCHEDULED: Publication.Status.SCHEDULED,
    },
    "cancel-schedule": {Publication.Status.SCHEDULED: Publication.Status.IN_REVIEW},
    "unpublish": {Publication.Status.PUBLISHED: Publication.Status.UNPUBLISHED},
    "archive": {Publication.Status.UNPUBLISHED: Publication.Status.ARCHIVED},
}


def _validate_ready(publication: Publication) -> None:
    if (
        not publication.title.strip()
        or not publication.summary.strip()
        or not publication.body_text
    ):
        raise ValidationError("Title, summary, and body are required.")
    if not publication.category.is_active:
        raise ValidationError("An active category is required.")
    if not AudienceRule.objects.filter(publication=publication).exists():
        raise ValidationError("At least one audience rule is required.")


def _apply_transition_locked(
    publication: Publication,
    *,
    action: str,
    actor: User,
    scheduled_for: datetime | None = None,
    expires_at: datetime | None = None,
    automated: bool = False,
) -> Publication:
    target = TRANSITIONS.get(action, {}).get(publication.status)
    if target is None:
        raise ValidationError(f"Transition {action} is not allowed from {publication.status}.")
    if not automated:
        if action == "submit-review":
            if publication.author.pk != actor.pk and not is_editor(actor):
                raise PermissionDenied("Only the author can submit this publication.")
        elif not is_editor(actor):
            raise PermissionDenied("An editor role is required for this transition.")
    if action in {"publish", "schedule"}:
        _validate_ready(publication)
    now = timezone.now()
    if action == "schedule":
        if scheduled_for is None or scheduled_for <= now:
            raise ValidationError("scheduled_for must be in the future.")
        if expires_at is not None and expires_at <= scheduled_for:
            raise ValidationError("expires_at must be later than scheduled_for.")
    previous = publication_snapshot(publication)
    publication.status = target
    publication.edit_revision += 1
    if action == "publish":
        publication.published_at = now
        publication.scheduled_for = None
        publication.unpublished_at = None
        if expires_at is not None:
            publication.expires_at = expires_at
    elif action == "schedule":
        publication.scheduled_for = scheduled_for
        publication.expires_at = expires_at
        publication.published_at = None
        publication.unpublished_at = None
    elif action == "cancel-schedule":
        publication.scheduled_for = None
    elif action == "unpublish":
        publication.unpublished_at = now
        PublicationPin.objects.filter(publication=publication).delete()
    elif action == "archive":
        publication.archived_at = now
        PublicationPin.objects.filter(publication=publication).delete()
    publication.full_clean()
    publication.save()
    if action == "publish":
        from .engagement import refresh_recipient_snapshot

        recipient_ids = [cast(Any, row).user_id for row in refresh_recipient_snapshot(publication)]
        from apps.notifications.models import Notification
        from apps.notifications.services import enqueue_fanout

        enqueue_fanout(
            event_key=f"publication:{publication.pk}:published:{publication.edit_revision}",
            event_type=Notification.Type.NEW_PUBLICATION,
            source_id=publication.pk,
            payload={"actor_id": actor.pk, "recipient_ids": recipient_ids},
        )
        if publication.acknowledgement_required:
            enqueue_fanout(
                event_key=f"publication:{publication.pk}:ack:{publication.edit_revision}",
                event_type=Notification.Type.ACK_REQUIRED,
                source_id=publication.pk,
                payload={"actor_id": actor.pk, "recipient_ids": recipient_ids},
            )
    event_type = {
        "publish": AuditEvent.Type.PUBLISHED,
        "submit-review": AuditEvent.Type.SUBMITTED_FOR_REVIEW,
        "return-to-draft": AuditEvent.Type.RETURNED_TO_DRAFT,
        "schedule": AuditEvent.Type.SCHEDULED,
        "cancel-schedule": AuditEvent.Type.SCHEDULE_CANCELLED,
        "unpublish": AuditEvent.Type.UNPUBLISHED,
        "archive": AuditEvent.Type.ARCHIVED,
    }[action]
    record_audit_event(
        publication=publication,
        actor=actor,
        event_type=event_type,
        target_type=AuditEvent.TargetType.PUBLICATION,
        target_id=publication.pk,
        previous_state=previous,
        new_state=publication_snapshot(publication),
    )
    create_version(publication, actor=actor, reason=f"lifecycle:{action}", previous=previous)
    return publication


@transaction.atomic
def transition_publication(
    publication: Publication,
    *,
    action: str,
    actor: User,
    expected_revision: int | None = None,
    scheduled_for: datetime | None = None,
    expires_at: datetime | None = None,
) -> Publication:
    publication = (
        Publication.objects.select_for_update()
        .select_related("category", "author")
        .get(pk=publication.pk)
    )
    if expected_revision is not None and publication.edit_revision != expected_revision:
        raise StaleRevisionError(publication.edit_revision)
    return _apply_transition_locked(
        publication,
        action=action,
        actor=actor,
        scheduled_for=scheduled_for,
        expires_at=expires_at,
    )


def publish_publication(publication: Publication, *, actor: User) -> Publication:
    return transition_publication(publication, action="publish", actor=actor)


@transaction.atomic
def reconcile_publications(*, now: datetime | None = None) -> dict[str, int]:
    timestamp = now or timezone.now()
    published = 0
    expired = 0
    due_ids = list(
        Publication.objects.filter(
            status=Publication.Status.SCHEDULED, scheduled_for__lte=timestamp
        ).values_list("pk", flat=True)
    )
    for publication in (
        Publication.objects.select_for_update(skip_locked=True)
        .select_related("category", "author")
        .filter(pk__in=due_ids)
    ):
        _apply_transition_locked(
            publication, action="publish", actor=publication.author, automated=True
        )
        published += 1
    expired_ids = list(
        Publication.objects.filter(
            status=Publication.Status.PUBLISHED, expires_at__lte=timestamp
        ).values_list("pk", flat=True)
    )
    for publication in (
        Publication.objects.select_for_update(skip_locked=True)
        .select_related("category", "author")
        .filter(pk__in=expired_ids)
    ):
        _apply_transition_locked(
            publication, action="unpublish", actor=publication.author, automated=True
        )
        expired += 1
    return {"published": published, "expired": expired}


@transaction.atomic
def pin_publication(publication: Publication, *, actor: User, slot: int) -> PublicationPin:
    if not is_editor(actor):
        raise PermissionDenied("An editor role is required.")
    publication = Publication.objects.select_for_update().get(pk=publication.pk)
    if publication.status != Publication.Status.PUBLISHED:
        raise ValidationError("Only published publications can be pinned.")
    if not 1 <= slot <= MAX_PINNED:
        raise ValidationError(f"Pin slot must be between 1 and {MAX_PINNED}.")
    occupied = PublicationPin.objects.select_for_update().filter(slot=slot).first()
    if occupied is not None and occupied.publication.pk != publication.pk:
        raise ValidationError("Pin slot is already occupied.")
    previous = PublicationPin.objects.filter(publication=publication).values("slot").first() or {}
    try:
        with transaction.atomic():
            pin, _ = PublicationPin.objects.update_or_create(
                publication=publication, defaults={"slot": slot, "pinned_by": actor}
            )
    except IntegrityError as exc:
        raise ValidationError("Pin slot is already occupied.") from exc
    record_audit_event(
        publication=publication,
        actor=actor,
        event_type=AuditEvent.Type.PINNED,
        target_type=AuditEvent.TargetType.PUBLICATION,
        target_id=publication.pk,
        previous_state=previous,
        new_state={"slot": pin.slot},
    )
    return pin


@transaction.atomic
def unpin_publication(publication: Publication, *, actor: User) -> None:
    if not is_editor(actor):
        raise PermissionDenied("An editor role is required.")
    publication = Publication.objects.select_for_update().get(pk=publication.pk)
    previous = PublicationPin.objects.filter(publication=publication).values("slot").first() or {}
    PublicationPin.objects.filter(publication=publication).delete()
    record_audit_event(
        publication=publication,
        actor=actor,
        event_type=AuditEvent.Type.UNPINNED,
        target_type=AuditEvent.TargetType.PUBLICATION,
        target_id=publication.pk,
        previous_state=previous,
    )


@transaction.atomic
def duplicate_publication(publication: Publication, *, actor: User) -> Publication:
    source = (
        Publication.objects.select_for_update()
        .select_related("category")
        .prefetch_related("tags", "media_usages__asset", "audience_rules")
        .get(pk=publication.pk)
    )
    if source.status == Publication.Status.ARCHIVED and not is_editor(actor):
        raise PermissionDenied("An editor role is required to duplicate archived material.")
    usages = list(source.media_usages.select_related("asset"))
    clone = create_publication(
        actor=actor,
        data={
            "title": f"{source.title} — копия",
            "summary": source.summary,
            "body": source.body,
            "category": source.category,
            "tags": list(source.tags.all()),
            "audience": audience_payload(source),
            "cover": source.cover,
            "body_assets": [u.asset for u in usages if u.purpose == MediaUsage.Purpose.BODY],
            "attachments": [u.asset for u in usages if u.purpose == MediaUsage.Purpose.ATTACHMENT],
            "comments_enabled": source.comments_enabled,
            "reactions_enabled": source.reactions_enabled,
            "acknowledgement_required": source.acknowledgement_required,
        },
    )
    record_audit_event(
        publication=clone,
        actor=actor,
        event_type=AuditEvent.Type.DUPLICATED,
        target_type=AuditEvent.TargetType.PUBLICATION,
        target_id=clone.pk,
        previous_state={"source_publication_id": str(source.pk)},
        new_state=publication_snapshot(clone),
    )
    return clone


def audience_payload(publication: Publication) -> AudiencePayload:
    rules = publication.audience_rules.select_related("org_unit", "employee").all()
    return {
        "everyone": any(rule.kind == AudienceRule.Kind.ALL for rule in rules),
        "org_units": [
            rule.org_unit.external_id
            for rule in rules
            if rule.kind == AudienceRule.Kind.ORG_UNIT and not rule.include_descendants
        ],
        "org_unit_subtrees": [
            rule.org_unit.external_id
            for rule in rules
            if rule.kind == AudienceRule.Kind.ORG_UNIT and rule.include_descendants
        ],
        "employees": [
            rule.employee.pk
            for rule in rules
            if rule.kind == AudienceRule.Kind.EMPLOYEE and rule.employee is not None
        ],
        "module_roles": [
            rule.module_role for rule in rules if rule.kind == AudienceRule.Kind.MODULE_ROLE
        ],
        "position_groups": [
            {
                "external_id": rule.position_group_external_id,
                "name": rule.position_group_name,
            }
            for rule in rules
            if rule.kind == AudienceRule.Kind.POSITION_GROUP
        ],
    }
