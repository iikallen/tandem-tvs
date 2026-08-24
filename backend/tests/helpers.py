from rest_framework.test import APIClient

from apps.identity.models import User
from apps.identity.portal import get_portal_adapter
from apps.identity.services import grant_legacy_roles, provision_user


def portal_fixture_user(portal_id: str) -> User | None:
    """Materialize a legacy portal fixture as local test data, never as authentication."""
    employee = get_portal_adapter().get_employee(portal_id)
    if employee is None:
        return None
    user = provision_user(get_portal_adapter(), employee)
    grant_legacy_roles(user, employee.roles)
    return user


def force_authenticate_portal_fixture(client: APIClient, portal_id: str) -> User | None:
    client.force_authenticate(user=None)
    user = portal_fixture_user(portal_id)
    if user is not None and user.is_active:
        client.force_authenticate(user=user)
    return user
