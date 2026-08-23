import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import TypedDict, cast

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.generics import get_object_or_404

from apps.identity.models import User
from apps.identity.portal import get_portal_adapter
from apps.identity.services import provision_user
from apps.organization.models import OrgUnit

from .models import MODULE_ROLE_MAX_LENGTH, AudienceRule, AuditEvent, Publication, PublicationView


def visible_publication_or_404(user: User, publication_id: object) -> Publication:
    """The single authorization boundary for publication child resources."""
    return get_object_or_404(Publication.objects.visible_to(user), pk=publication_id)


class AudiencePayload(TypedDict):
    everyone: bool
    org_units: list[str]
    employees: list[str]
    module_roles: list[str]


@transaction.atomic
def replace_audience_rules(
    publication: Publication,
    *,
    everyone: bool = False,
    org_units: Iterable[OrgUnit] = (),
    employees: Iterable[User] = (),
    module_roles: Iterable[str] = (),
) -> list[AudienceRule]:
    publication = Publication.objects.select_for_update().get(pk=publication.pk)
    units = {unit.external_id: unit for unit in org_units}
    users = {user.portal_id: user for user in employees}
    roles = {role.strip() for role in module_roles if role.strip()}

    if everyone and (units or users or roles):
        raise ValidationError("ALL audience cannot be combined with narrower rules.")
    if any(not unit.is_active for unit in units.values()):
        raise ValidationError("Inactive organization units cannot be audience targets.")
    if any(not user.is_active for user in users.values()):
        raise ValidationError("Inactive employees cannot be audience targets.")
    if any(len(role) > MODULE_ROLE_MAX_LENGTH for role in roles):
        raise ValidationError("Module role is too long.")

    rules = (
        [AudienceRule(publication=publication, kind=AudienceRule.Kind.ALL)]
        if everyone
        else [
            *(
                AudienceRule(
                    publication=publication,
                    kind=AudienceRule.Kind.ORG_UNIT,
                    org_unit=unit,
                )
                for unit in units.values()
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
        defaults={
            "first_viewed_at": timestamp,
            "last_viewed_at": timestamp,
        },
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
        "status": publication.status,
        "published_at": publication.published_at.isoformat() if publication.published_at else None,
        "audience": list(
            AudienceRule.objects.filter(publication=publication).values(
                "kind", "org_unit_id", "employee_id", "module_role"
            )
        ),
    }


def _slug_for(title: str, publication_id: uuid.UUID) -> str:
    base = slugify(title, allow_unicode=True)[:240] or "publication"
    if not Publication.objects.filter(slug=base).exists():
        return base
    return f"{base[:246]}-{publication_id.hex[:8]}"


def _audience_targets(payload: AudiencePayload):
    unit_ids = set(payload["org_units"])
    employee_ids = set(payload["employees"])
    units = list(OrgUnit.objects.filter(external_id__in=unit_ids, is_active=True))
    users = []
    if employee_ids:
        adapter = get_portal_adapter()
        for portal_id in employee_ids:
            employee = adapter.get_employee(portal_id)
            if employee is None or employee.portal_id != portal_id or not employee.is_active:
                raise ValidationError("Unknown or inactive employee audience target.")
            users.append(provision_user(adapter, employee))
    if {unit.external_id for unit in units} != unit_ids:
        raise ValidationError("Unknown or inactive organization audience target.")
    return units, users


def set_publication_audience(publication: Publication, payload: AudiencePayload) -> None:
    units, users = _audience_targets(payload)
    replace_audience_rules(
        publication,
        everyone=payload["everyone"],
        org_units=units,
        employees=users,
        module_roles=payload["module_roles"],
    )


@transaction.atomic
def create_publication(*, actor: User, data: dict[str, object]) -> Publication:
    audience = cast(AudiencePayload, data.pop("audience"))
    publication_id = uuid.uuid4()
    publication = Publication(
        id=publication_id,
        author=actor,
        slug=_slug_for(str(data["title"]), publication_id),
        **data,
    )
    publication.full_clean()
    publication.save()
    set_publication_audience(publication, audience)
    AuditEvent.objects.create(
        publication=publication,
        actor=actor,
        event_type=AuditEvent.Type.CREATED,
    )
    return publication


@transaction.atomic
def update_publication(
    publication: Publication,
    *,
    actor: User,
    data: dict[str, object],
) -> Publication:
    publication = Publication.objects.select_for_update().get(pk=publication.pk)
    if publication.status != Publication.Status.DRAFT:
        raise ValidationError("Published publications cannot be edited in Stage 2.")
    previous = publication_snapshot(publication)
    audience = cast(AudiencePayload | None, data.pop("audience", None))
    for field, value in data.items():
        setattr(publication, field, value)
    publication.full_clean()
    publication.save()
    if audience is not None:
        set_publication_audience(publication, audience)
    AuditEvent.objects.create(
        publication=publication,
        actor=actor,
        event_type=AuditEvent.Type.UPDATED,
        previous_state=previous,
    )
    return publication


@transaction.atomic
def publish_publication(publication: Publication, *, actor: User) -> Publication:
    publication = Publication.objects.select_for_update().get(pk=publication.pk)
    if publication.status != Publication.Status.DRAFT:
        raise ValidationError("Only drafts can be published.")
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
    previous = publication_snapshot(publication)
    publication.status = Publication.Status.PUBLISHED
    publication.published_at = timezone.now()
    publication.full_clean()
    publication.save(update_fields=["status", "published_at", "updated_at"])
    AuditEvent.objects.create(
        publication=publication,
        actor=actor,
        event_type=AuditEvent.Type.PUBLISHED,
        previous_state=previous,
    )
    return publication
