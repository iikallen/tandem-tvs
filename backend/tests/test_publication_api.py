from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.publications import services as publication_services
from apps.publications.models import (
    AudienceRule,
    AuditEvent,
    Category,
    Publication,
    PublicationView,
)
from tests.helpers import force_authenticate_portal_fixture


def body(text: str = "Подключайтесь безопасно") -> dict[str, object]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def draft_payload(**overrides):
    payload = {
        "title": "Регламент VPN",
        "summary": "Правила безопасного подключения",
        "body": body(),
        "category": "company",
        "audience": {
            "everyone": False,
            "org_units": ["engineering"],
            "employees": [],
            "module_roles": [],
        },
    }
    payload.update(overrides)
    return payload


def as_user(client: APIClient, settings, portal_id: str, method: str, path: str, data=None):
    force_authenticate_portal_fixture(client, portal_id)
    return getattr(client, method)(path, data, format="json")


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def category():
    return Category.objects.create(slug="company", name="Компания")


@pytest.mark.django_db
def test_editorial_api_is_role_protected_and_server_assigns_author(client, category, settings):
    denied = as_user(client, settings, "employee-1", "get", "/api/v1/editorial/publications")
    assert denied.status_code == 403

    forged = draft_payload(author="employee-1")
    rejected = as_user(
        client, settings, "editor-1", "post", "/api/v1/editorial/publications", forged
    )
    assert rejected.status_code == 400
    assert not Publication.objects.exists()

    created = as_user(
        client,
        settings,
        "editor-1",
        "post",
        "/api/v1/editorial/publications",
        draft_payload(),
    )
    assert created.status_code == 201
    assert created.data["author"]["portal_id"] == "editor-1"
    assert created.data["status"] == "DRAFT"
    assert created.data["audience"]["org_units"] == ["engineering"]
    assert AuditEvent.objects.values_list("event_type", flat=True).get() == "publication.created"
    assert "private" in created["Cache-Control"]


@pytest.mark.django_db
def test_administrator_can_create_a_publication(client, category, settings):
    created = as_user(
        client,
        settings,
        "admin-1",
        "post",
        "/api/v1/editorial/publications",
        draft_payload(audience={"everyone": True}),
    )
    assert created.status_code == 201
    assert created.data["author"]["portal_id"] == "admin-1"


@pytest.mark.django_db
def test_editor_update_publish_and_audit_are_transactional_and_append_only(
    client, category, settings
):
    created = as_user(
        client,
        settings,
        "editor-1",
        "post",
        "/api/v1/editorial/publications",
        draft_payload(),
    )
    publication_id = created.data["id"]
    updated = as_user(
        client,
        settings,
        "editor-1",
        "patch",
        f"/api/v1/editorial/publications/{publication_id}",
        {"title": "Новый регламент VPN", "expected_revision": created.data["edit_revision"]},
    )
    assert updated.status_code == 200
    assert updated.data["title"] == "Новый регламент VPN"

    published = as_user(
        client,
        settings,
        "editor-1",
        "post",
        f"/api/v1/editorial/publications/{publication_id}/publish",
    )
    assert published.status_code == 200
    assert published.data["status"] == "PUBLISHED"
    assert published.data["published_at"]
    assert list(AuditEvent.objects.values_list("event_type", flat=True)) == [
        "publication.created",
        "publication.updated",
        "publication.published",
    ]
    update_after_publish = as_user(
        client,
        settings,
        "editor-1",
        "patch",
        f"/api/v1/editorial/publications/{publication_id}",
        {
            "title": "Разрешённая правка редактора",
            "expected_revision": published.data["edit_revision"],
        },
    )
    assert update_after_publish.status_code == 200
    assert (
        as_user(
            client,
            settings,
            "editor-1",
            "post",
            f"/api/v1/editorial/publications/{publication_id}/publish",
        ).status_code
        == 400
    )

    event = AuditEvent.objects.first()
    assert event is not None
    event.previous_state = {"tampered": True}
    with pytest.raises(ValidationError, match="append-only"):
        event.save()
    with pytest.raises(ValidationError, match="append-only"):
        event.delete()
    with pytest.raises(ValidationError, match="append-only"):
        AuditEvent.objects.update(previous_state={"tampered": True})
    with pytest.raises(ValidationError, match="append-only"):
        AuditEvent.objects.all().delete()
    assert AuditEvent.objects.count() == 4


@pytest.mark.django_db
def test_publish_requires_complete_safe_content_active_category_and_audience(
    client, category, settings
):
    empty_audience = draft_payload(
        audience={"everyone": False, "org_units": [], "employees": [], "module_roles": []}
    )
    created = as_user(
        client,
        settings,
        "editor-1",
        "post",
        "/api/v1/editorial/publications",
        empty_audience,
    )
    assert created.status_code == 201
    assert (
        as_user(
            client,
            settings,
            "editor-1",
            "post",
            f"/api/v1/editorial/publications/{created.data['id']}/publish",
        ).status_code
        == 400
    )

    unsafe = draft_payload(body={"type": "doc", "content": [{"type": "script"}]})
    assert (
        as_user(
            client,
            settings,
            "editor-1",
            "post",
            "/api/v1/editorial/publications",
            unsafe,
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_addressed_feed_detail_search_unread_and_unique_views(client, category, settings):
    created = as_user(
        client,
        settings,
        "editor-1",
        "post",
        "/api/v1/editorial/publications",
        draft_payload(),
    )
    publication_id = created.data["id"]
    publish_path = f"/api/v1/editorial/publications/{publication_id}/publish"
    assert as_user(client, settings, "editor-1", "post", publish_path).status_code == 200

    engineering = as_user(client, settings, "admin-1", "get", "/api/v1/news")
    assert [item["id"] for item in engineering.data["results"]] == [publication_id]
    assert engineering.data["results"][0]["is_read"] is False
    assert engineering.data["results"][0]["comment_count"] == 0
    assert engineering.data["results"][0]["reaction_count"] == 0
    assert (
        as_user(client, settings, "admin-1", "get", "/api/v1/news", {"q": "безопасно"}).data[
            "results"
        ][0]["id"]
        == publication_id
    )
    assert (
        as_user(client, settings, "admin-1", "get", "/api/v1/news", {"unread": True}).data[
            "results"
        ][0]["id"]
        == publication_id
    )

    outsider = as_user(client, settings, "employee-1", "get", "/api/v1/news")
    assert outsider.data["results"] == []
    assert (
        as_user(client, settings, "employee-1", "get", "/api/v1/news", {"q": "VPN"}).data["results"]
        == []
    )
    assert (
        as_user(client, settings, "employee-1", "get", f"/api/v1/news/{publication_id}").status_code
        == 404
    )

    detail_path = f"/api/v1/news/{publication_id}"
    first = as_user(client, settings, "admin-1", "get", detail_path)
    second = as_user(client, settings, "admin-1", "get", detail_path)
    assert first.status_code == second.status_code == 200
    assert first.data["body"] == body()
    assert second.data["view_count"] == 1
    assert PublicationView.objects.count() == 1
    assert (
        as_user(client, settings, "admin-1", "get", "/api/v1/news", {"unread": True}).data[
            "results"
        ]
        == []
    )


@pytest.mark.django_db
def test_employee_audience_provisions_portal_target_before_first_visit(client, category, settings):
    payload = draft_payload(
        title="Личное сообщение",
        audience={
            "everyone": False,
            "org_units": [],
            "employees": ["employee-1"],
            "module_roles": [],
        },
    )
    created = as_user(
        client,
        settings,
        "editor-1",
        "post",
        "/api/v1/editorial/publications",
        payload,
    )
    assert created.status_code == 201
    assert User.objects.filter(portal_id="employee-1", is_active=True).exists()
    assert (
        as_user(
            client,
            settings,
            "editor-1",
            "post",
            f"/api/v1/editorial/publications/{created.data['id']}/publish",
        ).status_code
        == 200
    )
    addressed = as_user(client, settings, "employee-1", "get", "/api/v1/news")
    outsider = as_user(client, settings, "admin-1", "get", "/api/v1/news")
    assert [item["title"] for item in addressed.data["results"]] == ["Личное сообщение"]
    assert outsider.data["results"] == []


@pytest.mark.django_db
def test_employee_audience_rejects_adapter_identity_substitution(
    client, category, settings, monkeypatch
):
    class SubstitutingAdapter:
        def get_employee(self, portal_id):
            return SimpleNamespace(portal_id="admin-1", is_active=True)

    monkeypatch.setattr(
        publication_services,
        "get_portal_adapter",
        lambda: SubstitutingAdapter(),
    )
    response = as_user(
        client,
        settings,
        "editor-1",
        "post",
        "/api/v1/editorial/publications",
        draft_payload(
            audience={
                "everyone": False,
                "org_units": [],
                "employees": ["employee-1"],
                "module_roles": [],
            }
        ),
    )
    assert response.status_code == 400
    assert not Publication.objects.exists()


@pytest.mark.django_db
def test_feed_filters_cursor_bounds_categories_and_blocked_identity(client, category, settings):
    as_user(client, settings, "editor-1", "get", "/api/v1/me")
    author = User.objects.get(portal_id="editor-1")
    now = timezone.now()
    for index in range(23):
        publication = Publication.objects.create(
            title=f"News {index}",
            slug=f"news-{index}",
            summary="Summary",
            body=body(f"Body {index}"),
            category=category,
            author=author,
            status=Publication.Status.PUBLISHED,
            published_at=now - timedelta(minutes=index),
        )
        AudienceRule.objects.create(publication=publication, kind="ALL")

    first = as_user(client, settings, "employee-1", "get", "/api/v1/news", {"page_size": 5})
    assert first.status_code == 200
    assert len(first.data["results"]) == 5
    assert first.data["next"]
    next_query = parse_qs(urlparse(first.data["next"]).query)
    second = as_user(
        client,
        settings,
        "employee-1",
        "get",
        "/api/v1/news",
        {"page_size": 5, "cursor": next_query["cursor"][0]},
    )
    assert not {item["id"] for item in first.data["results"]}.intersection(
        item["id"] for item in second.data["results"]
    )

    filtered = as_user(
        client,
        settings,
        "employee-1",
        "get",
        "/api/v1/news",
        {
            "category": "company",
            "author": "editor-1",
            "date_from": now.date().isoformat(),
            "date_to": now.date().isoformat(),
        },
    )
    assert filtered.status_code == 200
    assert filtered.data["results"]
    assert (
        as_user(
            client, settings, "employee-1", "get", "/api/v1/news", {"page_size": 51}
        ).status_code
        == 400
    )
    assert (
        as_user(client, settings, "employee-1", "get", "/api/v1/news", {"q": "x" * 201}).status_code
        == 400
    )
    categories = as_user(client, settings, "employee-1", "get", "/api/v1/news/categories")
    assert categories.data[0]["slug"] == "company"
    assert as_user(client, settings, "blocked-1", "get", "/api/v1/news").status_code == 403
