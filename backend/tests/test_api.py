import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.identity.managers import UserManager
from apps.identity.models import AccessGrant, User
from apps.identity.portal.types import PortalEmployee, PortalPositionGroup
from apps.organization import views as organization_views
from tests.helpers import force_authenticate_portal_fixture


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="employee-1")
def test_me_returns_read_only_portal_projection(client):
    force_authenticate_portal_fixture(client, "employee-1")
    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.data["username"] == "employee-1"
    assert response.data["portal_id"] == "employee-1"
    assert response.data["full_name"] == "Алия Байжанова"
    assert response.data["email"] == "a.baizhanova@tandem.example"
    assert response.data["org_unit"]["external_id"] == "communications"
    assert response.data["access"]["news"] == ["MEMBER"]
    assert response.data["access"]["messenger"] == ["MEMBER"]
    assert_private_no_store(response)
    assert client.patch("/api/v1/me", {"full_name": "Подмена"}).status_code == 405


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="blocked-1")
def test_blocked_employee_receives_stable_backend_error(client):
    force_authenticate_portal_fixture(client, "blocked-1")
    response = client.get("/api/v1/me")
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="unknown-1")
def test_unknown_employee_is_unauthorized(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="")
def test_missing_identity_is_unauthorized(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 403
    assert response.data["error"]["code"] == "not_authenticated"


@pytest.mark.django_db
def test_me_does_not_depend_on_portal_authentication(client):
    force_authenticate_portal_fixture(client, "employee-1")
    response = client.get("/api/v1/me")
    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(PORTAL_ADAPTER="unavailable", ALLOW_MOCK_PORTAL_ADAPTER=False)
def test_unavailable_adapter_does_not_break_local_session(client):
    manager = User.objects
    assert isinstance(manager, UserManager)
    user = manager.create_user(username="local-user", full_name="Local user")
    AccessGrant.objects.create(user=user, module="NEWS", role="MEMBER")
    client.force_authenticate(user)
    response = client.get("/api/v1/me")
    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="employee-1")
def test_organization_units_and_employee_search_are_authenticated(client):
    force_authenticate_portal_fixture(client, "employee-1")
    units_response = client.get("/api/v1/organization/units")
    assert units_response.status_code == 200
    assert {unit["external_id"] for unit in units_response.data} == {
        "company",
        "communications",
        "engineering",
    }
    assert_private_no_store(units_response)

    employees_response = client.get(
        "/api/v1/organization/employees",
        {"search": "Орлов"},
    )
    assert employees_response.status_code == 200
    assert [employee["portal_id"] for employee in employees_response.data] == ["editor-1"]
    assert all(employee["portal_id"] != "blocked-1" for employee in employees_response.data)
    assert employees_response.data == [
        {
            "portal_id": "editor-1",
            "full_name": "Дмитрий Орлов",
            "job_title": "Редактор",
            "org_unit_external_id": "communications",
        }
    ]
    assert_private_no_store(employees_response)


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="employee-1")
def test_employee_search_is_query_bounded_and_data_minimized(client, monkeypatch):
    force_authenticate_portal_fixture(client, "employee-1")
    captured: dict[str, object] = {}

    class SearchAdapter:
        def search_employees(self, query, *, limit):
            captured.update(query=query, limit=limit)
            return tuple(
                PortalEmployee(
                    portal_id=f"employee-{index}",
                    full_name=f"Employee {index}",
                    is_active=True,
                    email=f"employee-{index}@example.invalid",
                    phone="secret",
                    roles=("employee", "private-role"),
                )
                for index in range(25)
            )

    monkeypatch.setattr(organization_views, "get_portal_adapter", SearchAdapter)

    assert client.get("/api/v1/organization/employees").data == []
    assert client.get("/api/v1/organization/employees", {"search": "x"}).data == []
    assert (
        client.get(
            "/api/v1/organization/employees",
            {"search": "x" * 101},
        ).status_code
        == 400
    )

    response = client.get("/api/v1/organization/employees", {"search": "Employee"})

    assert response.status_code == 200
    assert len(response.data) == 20
    assert captured == {"query": "Employee", "limit": 20}
    assert set(response.data[0]) == {
        "portal_id",
        "full_name",
        "job_title",
        "org_unit_external_id",
    }


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="employee-1")
def test_position_groups_are_portal_only_active_and_canonical(client, monkeypatch):
    force_authenticate_portal_fixture(client, "employee-1")
    User.objects.create(
        portal_id="local-only",
        full_name="Local only",
        position_group_external_id="local-group",
        position_group_name="Local group",
    )

    class GroupAdapter:
        def list_position_groups(self):
            return (
                PortalPositionGroup("editors", "Редакторы"),
                PortalPositionGroup("inactive", "Неактивные", is_active=False),
                PortalPositionGroup("authors", "Авторы"),
            )

    monkeypatch.setattr(organization_views, "get_portal_adapter", GroupAdapter)
    response = client.get("/api/v1/organization/position-groups")

    assert response.status_code == 200
    assert response.data == [
        {"external_id": "authors", "name": "Авторы"},
        {"external_id": "editors", "name": "Редакторы"},
    ]
    assert "local-group" not in str(response.data)


@pytest.mark.django_db
@override_settings(MOCK_PORTAL_USER_ID="")
def test_public_health_and_runtime_do_not_create_a_user(client):
    assert client.get("/api/v1/health/live").data == {"status": "ok"}

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    assert ready.data["components"] == {"database": "ok", "cache": "ok", "portal": "ok"}

    runtime = client.get("/api/v1/runtime/meta")
    assert runtime.status_code == 200
    assert runtime.data["supported_locales"] == ["ru"]
    assert runtime.data["planned_locales"] == ["kk"]

    assert not User.objects.exists()


@pytest.mark.django_db
def test_schema_and_docs_require_identity_and_use_local_assets(client, settings):
    assert client.get("/api/schema").status_code == 403
    assert client.get("/api/docs").status_code == 403

    force_authenticate_portal_fixture(client, "employee-1")
    schema = client.get("/api/schema")
    docs = client.get("/api/docs")

    assert schema.status_code == 200
    assert b"/api/v1/me" in schema.content
    assert docs.status_code == 200
    assert b"drf_spectacular_sidecar" in docs.content
    assert b"cdn.jsdelivr" not in docs.content

    swagger_css = client.get("/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui.css")
    assert swagger_css.status_code == 200
    assert swagger_css["Content-Type"].startswith("text/css")


def test_no_legacy_or_token_auth_routes_exist(client):
    for path in ("/register", "/api/token"):
        assert client.get(path).status_code == 404


def assert_private_no_store(response):
    directives = {directive.strip() for directive in response["Cache-Control"].split(",")}
    assert {"private", "no-store", "max-age=0"} <= directives
