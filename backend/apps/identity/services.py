from django.db import transaction
from django.utils import timezone

from apps.organization.models import OrgUnit

from .models import User
from .portal.base import PortalAdapter
from .portal.types import PortalEmployee


def sync_org_units(adapter: PortalAdapter) -> dict[str, OrgUnit]:
    portal_units = adapter.list_org_units()
    units: dict[str, OrgUnit] = {}

    for portal_unit in portal_units:
        unit, _ = OrgUnit.objects.update_or_create(
            external_id=portal_unit.external_id,
            defaults={
                "name": portal_unit.name,
                "kind": portal_unit.kind,
                "is_active": portal_unit.is_active,
            },
        )
        units[portal_unit.external_id] = unit

    for portal_unit in portal_units:
        unit = units[portal_unit.external_id]
        parent = (
            units.get(portal_unit.parent_external_id)
            if portal_unit.parent_external_id is not None
            else None
        )
        if unit.parent != parent:
            unit.parent = parent
            unit.save(update_fields=["parent", "updated_at"])

    return units


def provision_user(adapter: PortalAdapter, employee: PortalEmployee) -> User:
    with transaction.atomic():
        units = sync_org_units(adapter)
        user, _ = User.objects.get_or_create(
            portal_id=employee.portal_id,
            defaults={"full_name": employee.full_name},
        )
        user.email = employee.email
        user.full_name = employee.full_name
        user.job_title = employee.job_title
        user.phone = employee.phone
        user.avatar_url = employee.avatar_url
        user.org_unit = (
            units.get(employee.org_unit_external_id)
            if employee.org_unit_external_id is not None
            else None
        )
        user.module_roles = list(employee.roles)
        user.is_active = employee.is_active
        user.last_portal_sync_at = timezone.now()
        user.set_unusable_password()
        user.save()
        return user


def deactivate_projection(portal_id: str) -> None:
    User.objects.filter(portal_id=portal_id).update(
        is_active=False,
        last_portal_sync_at=timezone.now(),
    )
