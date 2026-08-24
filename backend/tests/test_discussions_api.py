from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.discussions.models import Comment, Reaction
from apps.identity.models import User
from apps.publications.models import AudienceRule, Category, Publication, PublicationView
from apps.publications.views import employee_news_queryset


def as_user(client: APIClient, settings, portal_id: str, method: str, path: str, data=None):
    settings.MOCK_PORTAL_USER_ID = portal_id
    return getattr(client, method)(path, data, format="json")


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def publication(client, settings):
    as_user(client, settings, "editor-1", "get", "/api/v1/me")
    author = User.objects.get(portal_id="editor-1")
    category = Category.objects.create(slug="stage3", name="Stage 3")
    item = Publication.objects.create(
        title="Stage 3",
        slug="stage-3",
        summary="Discussion",
        body={"type": "doc", "content": [{"type": "paragraph", "content": []}]},
        category=category,
        author=author,
        status=Publication.Status.PUBLISHED,
        published_at=timezone.now() - timedelta(minutes=1),
    )
    AudienceRule.objects.create(publication=item, kind=AudienceRule.Kind.ALL)
    return item


@pytest.mark.django_db
def test_comment_lifecycle_normalization_ownership_and_deleted_body(client, publication, settings):
    path = f"/api/v1/news/{publication.pk}/comments"
    created = as_user(
        client, settings, "employee-1", "post", path, {"body": " hello\r\nworld\x00 "}
    )
    assert created.status_code == 201
    assert created.data["body"] == "hello\nworld"
    assert created.data["author"]["portal_id"] == "employee-1"
    assert "no-store" in created["Cache-Control"]
    comment_id = created.data["id"]

    forged = as_user(
        client,
        settings,
        "employee-1",
        "patch",
        f"{path}/{comment_id}",
        {"body": "changed", "author": "admin-1"},
    )
    assert forged.status_code == 400
    denied = as_user(client, settings, "admin-1", "patch", f"{path}/{comment_id}", {"body": "mine"})
    assert denied.status_code == 403
    updated = as_user(
        client,
        settings,
        "employee-1",
        "patch",
        f"{path}/{comment_id}",
        {"body": "changed"},
    )
    assert updated.status_code == 200
    assert updated.data["edited_at"]

    assert (
        as_user(client, settings, "employee-1", "delete", f"{path}/{comment_id}").status_code == 204
    )
    assert (
        as_user(client, settings, "employee-1", "delete", f"{path}/{comment_id}").status_code == 204
    )
    listed = as_user(client, settings, "employee-1", "get", path)
    assert listed.data["results"][0]["status"] == "DELETED"
    assert listed.data["results"][0]["body"] is None
    stored = Comment.objects.get(pk=comment_id)
    assert stored.body == ""
    assert stored.deleted_at is not None
    assert str(stored).startswith(str(publication.pk))
    assert (
        as_user(
            client,
            settings,
            "employee-1",
            "patch",
            f"{path}/{comment_id}",
            {"body": "too late"},
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_comments_validate_body_page_size_and_stable_cursor(client, publication, settings):
    path = f"/api/v1/news/{publication.pk}/comments"
    assert (
        as_user(client, settings, "employee-1", "post", path, {"body": " \x00 "}).status_code == 400
    )
    assert (
        as_user(client, settings, "employee-1", "post", path, {"body": "x" * 5001}).status_code
        == 400
    )
    user = as_user(client, settings, "employee-1", "get", "/api/v1/me")
    assert user.status_code == 200
    author = User.objects.get(portal_id="employee-1")
    Comment.objects.bulk_create(
        [
            Comment(publication=publication, author=author, body=f"comment {index}")
            for index in range(31)
        ]
    )
    first = as_user(client, settings, "employee-1", "get", path)
    assert len(first.data["results"]) == 20
    assert first.data["next"]
    clamped = as_user(client, settings, "employee-1", "get", path, {"page_size": 101})
    assert clamped.status_code == 200
    assert len(clamped.data["results"]) <= 100


@pytest.mark.django_db
def test_reactions_are_like_only_idempotent_and_real_counters(client, publication, settings):
    base = f"/api/v1/news/{publication.pk}/reactions"
    like = f"{base}/LIKE"
    assert as_user(client, settings, "employee-1", "put", like).status_code == 201
    assert as_user(client, settings, "employee-1", "put", like).status_code == 200
    assert Reaction.objects.count() == 1
    assert str(Reaction.objects.get()).endswith("LIKE")
    summary = as_user(client, settings, "employee-1", "get", base)
    assert summary.data["total"] == 1
    assert summary.data["counts"] == {"LIKE": 1}
    assert summary.data["mine"] == ["LIKE"]
    assert summary.data["actors"]["LIKE"][0]["portal_id"] == "employee-1"
    feed = as_user(client, settings, "employee-1", "get", "/api/v1/news")
    assert feed.data["results"][0]["reaction_count"] == 1
    assert as_user(client, settings, "employee-1", "put", f"{base}/FIRE").status_code == 404
    assert as_user(client, settings, "employee-1", "delete", like).status_code == 204
    assert as_user(client, settings, "employee-1", "delete", like).status_code == 204
    assert Reaction.objects.count() == 0


@pytest.mark.django_db
def test_feed_counts_use_independent_subqueries_without_join_multiplication(
    client, publication, settings
):
    for portal_id in ("employee-1", "admin-1"):
        assert as_user(client, settings, portal_id, "get", "/api/v1/me").status_code == 200
    employee = User.objects.get(portal_id="employee-1")
    admin = User.objects.get(portal_id="admin-1")
    Comment.objects.bulk_create(
        [
            Comment(publication=publication, author=employee, body=f"comment {index}")
            for index in range(3)
        ]
    )
    Reaction.objects.bulk_create(
        [
            Reaction(publication=publication, user=user, reaction_type=Reaction.Type.LIKE)
            for user in (employee, admin, publication.author)
        ]
    )
    PublicationView.objects.bulk_create(
        [
            PublicationView(
                publication=publication,
                user=user,
                first_viewed_at=timezone.now(),
                last_viewed_at=timezone.now(),
            )
            for user in (employee, admin)
        ]
    )

    queryset = employee_news_queryset(employee).filter(pk=publication.pk)
    sql = str(queryset.query).upper()
    assert 'JOIN "DISCUSSIONS_COMMENT"' not in sql
    assert 'JOIN "DISCUSSIONS_REACTION"' not in sql
    assert 'JOIN "PUBLICATIONS_PUBLICATIONVIEW"' not in sql
    result = queryset.get()
    assert (result.view_count, result.comment_count, result.reaction_count) == (2, 3, 3)


@pytest.mark.django_db
def test_comment_body_requires_string(client, publication, settings):
    path = f"/api/v1/news/{publication.pk}/comments"
    assert as_user(client, settings, "employee-1", "post", path, {"body": 7}).status_code == 400


@pytest.mark.django_db
def test_visibility_boundary_hides_discussions_reactions_and_tickets(
    client, publication, settings, monkeypatch
):
    publication.audience_rules.all().delete()
    AudienceRule.objects.create(
        publication=publication, kind=AudienceRule.Kind.ORG_UNIT, org_unit_id="engineering"
    )
    paths = [
        f"/api/v1/news/{publication.pk}/comments",
        f"/api/v1/news/{publication.pk}/reactions",
    ]
    for path in paths:
        assert as_user(client, settings, "employee-1", "get", path).status_code == 404
    monkeypatch.setattr("apps.discussions.views.create_ticket", lambda **kwargs: ("token", 30))
    assert (
        as_user(
            client,
            settings,
            "employee-1",
            "post",
            "/api/v1/realtime/tickets",
            {"publication_id": str(publication.pk)},
        ).status_code
        == 404
    )
    assert as_user(client, settings, "blocked-1", "get", paths[0]).status_code == 403


@pytest.mark.django_db
def test_ticket_api_is_server_scoped_and_no_store(client, publication, settings, monkeypatch):
    captured = {}

    def fake_create_ticket(**kwargs):
        captured.update(kwargs)
        return "opaque", 30

    monkeypatch.setattr("apps.discussions.views.create_ticket", fake_create_ticket)
    response = as_user(
        client,
        settings,
        "employee-1",
        "post",
        "/api/v1/realtime/tickets",
        {"publication_id": str(publication.pk)},
    )
    assert response.status_code == 200
    assert response.data == {"ticket": "opaque", "expires_in": 30}
    assert captured["user_id"] == User.objects.get(portal_id="employee-1").pk
    assert "no-store" in response["Cache-Control"]
    assert (
        as_user(
            client,
            settings,
            "employee-1",
            "post",
            "/api/v1/realtime/tickets",
            {"publication_id": str(publication.pk), "user_id": 999},
        ).status_code
        == 400
    )
    assert (
        as_user(client, settings, "employee-1", "post", "/api/v1/realtime/tickets", {}).status_code
        == 400
    )
    assert (
        as_user(
            client,
            settings,
            "employee-1",
            "post",
            "/api/v1/realtime/tickets",
            {"publication_id": "not-a-uuid"},
        ).status_code
        == 400
    )
    assert (
        as_user(
            client,
            settings,
            "employee-1",
            "post",
            "/api/v1/realtime/tickets",
            [],
        ).status_code
        == 400
    )
