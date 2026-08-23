import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.identity import authentication
from apps.identity.models import User
from apps.identity.portal import PortalUnavailableError


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="employee-1")
def test_me_returns_read_only_portal_projection(client):
    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.data == {
        "portal_id": "employee-1",
        "full_name": "Алия Байжанова",
        "email": "a.baizhanova@tandem.example",
        "job_title": "Специалист",
        "phone": "+7 700 000 00 01",
        "avatar_url": "",
        "org_unit": {
            "external_id": "communications",
            "name": "Корпоративные коммуникации",
            "kind": "department",
            "parent_external_id": "company",
        },
        "module_roles": ["employee"],
    }
    assert client.patch("/api/v1/me", {"full_name": "Подмена"}).status_code == 405


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="blocked-1")
def test_blocked_employee_receives_stable_backend_error(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 403
    assert response.data["error"]["code"] == "portal_account_blocked"


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="unknown-1")
def test_unknown_employee_is_unauthorized(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.data["error"]["code"] == "unknown_portal_identity"


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="")
def test_missing_identity_is_unauthorized(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.data["error"]["code"] == "not_authenticated"


@pytest.mark.django_db
def test_portal_outage_returns_stable_service_unavailable(client, monkeypatch):
    class FailingAdapter:
        def authenticate_request(self, request):
            raise PortalUnavailableError

    monkeypatch.setattr(authentication, "get_portal_adapter", FailingAdapter)

    response = client.get("/api/v1/me")

    assert response.status_code == 503
    assert response.data == {
        "error": {
            "code": "portal_unavailable",
            "message": "Portal is temporarily unavailable.",
        }
    }


@pytest.mark.django_db
@override_settings(PORTAL_ADAPTER="unavailable", ALLOW_MOCK_PORTAL_ADAPTER=False)
def test_unavailable_adapter_returns_stable_service_unavailable(client):
    response = client.get("/api/v1/me")

    assert response.status_code == 503
    assert response.data["error"]["code"] == "portal_unavailable"


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="employee-1")
def test_organization_units_and_employee_search_are_authenticated(client):
    units_response = client.get("/api/v1/organization/units")
    assert units_response.status_code == 200
    assert {unit["external_id"] for unit in units_response.data} == {
        "company",
        "communications",
        "engineering",
    }

    employees_response = client.get(
        "/api/v1/organization/employees",
        {"search": "Орлов"},
    )
    assert employees_response.status_code == 200
    assert [employee["portal_id"] for employee in employees_response.data] == ["editor-1"]
    assert all(employee["portal_id"] != "blocked-1" for employee in employees_response.data)


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="")
def test_public_health_runtime_and_schema_do_not_create_a_user(client):
    assert client.get("/api/v1/health/live").data == {"status": "ok"}

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.data["components"] == {"database": "ok", "cache": "ok", "portal": "ok"}

    runtime = client.get("/api/v1/runtime/meta")
    assert runtime.status_code == 200
    assert runtime.data["supported_locales"] == ["ru"]
    assert runtime.data["planned_locales"] == ["kk"]

    schema = client.get("/api/schema")
    assert schema.status_code == 200
    assert b"/api/v1/me" in schema.content
    assert not User.objects.exists()


def test_no_local_identity_routes_exist(client):
    for path in ("/login", "/register", "/password-reset", "/api/token"):
        assert client.get(path).status_code == 404
