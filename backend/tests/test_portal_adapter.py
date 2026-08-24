from types import SimpleNamespace

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.identity.portal.exceptions import PortalUnavailableError
from apps.identity.portal.factory import get_portal_adapter
from apps.identity.portal.mock import MockPortalAdapter
from apps.identity.portal.types import PortalIdentity
from apps.identity.portal.unavailable import UnavailablePortalAdapter


@pytest.fixture
def adapter():
    return MockPortalAdapter()


def test_adapter_contract_has_stable_identity_and_directory_data(adapter):
    identity = adapter.authenticate_request(SimpleNamespace(_mock_portal_id="employee-1"))
    assert identity == PortalIdentity(portal_id="employee-1")

    employee = adapter.get_employee(identity.portal_id)
    assert employee is not None
    assert employee.full_name
    assert employee.is_active
    assert employee.org_unit_external_id

    units = adapter.list_org_units()
    assert {unit.external_id for unit in units} >= {"company", "communications"}
    assert any(unit.parent_external_id == "company" for unit in units)
    groups = adapter.list_position_groups()
    assert {group.external_id for group in groups if group.is_active} >= {
        "specialists",
        "communications-editors",
    }


def test_adapter_contract_covers_roles_blocked_user_search_and_health(adapter):
    assert adapter.get_employee("author-1").roles == ("employee", "author")
    assert adapter.get_employee("blocked-1").is_active is False
    assert adapter.get_employee("unknown") is None
    assert [employee.portal_id for employee in adapter.search_employees("Орлов", limit=20)] == [
        "editor-1"
    ]
    assert adapter.healthcheck().available is True


def test_mock_identity_is_not_read_from_public_headers(adapter, settings):
    settings.MOCK_PORTAL_USER_ID = "employee-1"
    request = SimpleNamespace(headers={"X-Portal-User": "admin-1"})
    assert adapter.authenticate_request(request) == PortalIdentity(portal_id="employee-1")


@override_settings(PORTAL_ADAPTER="mock", ALLOW_MOCK_PORTAL_ADAPTER=False)
def test_mock_adapter_is_rejected_when_environment_disallows_it():
    with pytest.raises(ImproperlyConfigured, match="forbidden"):
        get_portal_adapter()


@override_settings(PORTAL_ADAPTER="unavailable", ALLOW_MOCK_PORTAL_ADAPTER=False)
def test_unavailable_adapter_is_supported_and_fails_closed():
    adapter = get_portal_adapter()

    assert isinstance(adapter, UnavailablePortalAdapter)
    with pytest.raises(PortalUnavailableError):
        adapter.get_employee("employee-1")
    with pytest.raises(PortalUnavailableError):
        adapter.list_position_groups()
    assert adapter.healthcheck().available is False
