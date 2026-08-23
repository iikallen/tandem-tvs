from collections.abc import Iterable
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.identity.models import User
from apps.organization.models import OrgUnit

from .models import MODULE_ROLE_MAX_LENGTH, AudienceRule, Publication, PublicationView


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
