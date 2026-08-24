import pytest
from rest_framework.test import APIClient

from apps.identity.backends import CaseInsensitiveModelBackend
from apps.identity.managers import UserManager
from apps.identity.models import AccessGrant, User
from apps.identity.portal.mock import MockPortalAdapter
from apps.identity.portal.types import PortalOrgUnit
from apps.identity.services import provision_user, sync_org_units
from apps.organization.models import OrgUnit


def create_user(**fields) -> User:
    manager = User.objects
    assert isinstance(manager, UserManager)
    return manager.create_user(**fields)


@pytest.mark.django_db
def test_local_backend_authenticates_case_insensitively():
    user = create_user(
        username="Local.Editor",
        password="correct horse battery staple",
        full_name="Local Editor",
    )

    authenticated = CaseInsensitiveModelBackend().authenticate(
        None,
        username="LOCAL.EDITOR",
        password="correct horse battery staple",
    )

    assert authenticated == user
    assert (
        CaseInsensitiveModelBackend().authenticate(None, username="local.editor", password="wrong")
        is None
    )


@pytest.mark.django_db
def test_inactive_local_user_cannot_authenticate():
    create_user(
        username="blocked",
        password="correct horse battery staple",
        full_name="Blocked",
        is_active=False,
    )
    assert (
        CaseInsensitiveModelBackend().authenticate(
            None, username="blocked", password="correct horse battery staple"
        )
        is None
    )


@pytest.mark.django_db
def test_portal_header_cannot_authenticate_a_request():
    response = APIClient().get("/api/v1/me", HTTP_X_MOCK_PORTAL_USER="employee-1")

    assert response.status_code == 403
    assert not User.objects.exists()


@pytest.mark.django_db
def test_portal_projection_sync_does_not_overwrite_local_security_state():
    adapter = MockPortalAdapter()
    employee = adapter.get_employee("employee-1")
    assert employee is not None
    user = create_user(
        username="employee-1",
        portal_id="employee-1",
        password="correct horse battery staple",
        full_name="Outdated",
        is_active=False,
    )
    AccessGrant.objects.create(user=user, module="NEWS", role="EDITOR")

    provision_user(adapter, employee)
    user.refresh_from_db()

    assert user.full_name == "Алия Байжанова"
    assert user.email == "a.baizhanova@tandem.example"
    assert user.org_unit.external_id == "communications"
    assert user.check_password("correct horse battery staple")
    assert user.is_active is False
    assert list(AccessGrant.objects.filter(user=user).values_list("module", "role")) == [
        ("NEWS", "EDITOR")
    ]


@pytest.mark.django_db
def test_org_unit_sync_deactivates_omissions_and_reactivates_returned_units():
    OrgUnit.objects.create(external_id="stale", name="Старое подразделение")

    class SnapshotAdapter:
        def __init__(self, units):
            self.units = units

        def list_org_units(self):
            return self.units

    sync_org_units(
        SnapshotAdapter((PortalOrgUnit(external_id="company", name="Tandem", kind="company"),))
    )

    assert OrgUnit.objects.get(external_id="stale").is_active is False

    sync_org_units(
        SnapshotAdapter(
            (
                PortalOrgUnit(external_id="company", name="Tandem", kind="company"),
                PortalOrgUnit(
                    external_id="stale",
                    name="Возвращённое подразделение",
                    kind="department",
                    parent_external_id="company",
                ),
            )
        )
    )

    restored = OrgUnit.objects.get(external_id="stale")
    assert restored.is_active is True
    assert restored.name == "Возвращённое подразделение"
    assert restored.parent.external_id == "company"
