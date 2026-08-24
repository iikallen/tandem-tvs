from datetime import timedelta
from uuid import UUID

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.identity.managers import UserManager
from apps.identity.models import AccessGrant, User
from apps.identity.services import grant_legacy_roles
from apps.organization.models import OrgUnit
from apps.publications.models import AudienceRule, Category, Publication, PublicationView
from apps.publications.rich_text import rich_text_to_plain_text, validate_rich_text_document
from apps.publications.services import record_publication_view, replace_audience_rules


def create_user(portal_id: str, *, active: bool = True) -> User:
    manager = User.objects
    assert isinstance(manager, UserManager)
    return manager.create_user(
        portal_id=portal_id,
        full_name=portal_id,
        is_active=active,
    )


def publish(publication: Publication) -> Publication:
    publication.status = Publication.Status.PUBLISHED
    publication.published_at = timezone.now()
    publication.save(update_fields=["status", "published_at"])
    return publication


def rich_body() -> dict[str, object]:
    return {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [
                    {"type": "text", "text": "  Регламент VPN  ", "marks": [{"type": "bold"}]}
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Подключайтесь   безопасно."},
                    {"type": "hardBreak"},
                    {
                        "type": "text",
                        "text": "Инструкция",
                        "marks": [
                            {
                                "type": "link",
                                "attrs": {
                                    "href": "/help/vpn",
                                    "target": "_self",
                                    "rel": None,
                                    "class": None,
                                },
                            }
                        ],
                    },
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Один пункт",
                                        "marks": [{"type": "italic"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "type": "blockquote",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Важная цитата"}],
                    }
                ],
            },
        ],
    }


def create_publication(*, author: User | None = None) -> Publication:
    author = author or create_user("author-1")
    category = Category.objects.create(slug="company", name="Компания")
    return Publication.objects.create(
        title="Регламент VPN",
        slug="reglament-vpn",
        summary="Правила безопасного подключения",
        body=rich_body(),
        body_text="forged client value",
        category=category,
        author=author,
    )


@pytest.mark.django_db
def test_publication_uses_uuid_minimal_statuses_and_server_generated_body_text():
    publication = create_publication()

    assert isinstance(publication.pk, UUID)
    assert Publication.Status.values == [
        "DRAFT",
        "IN_REVIEW",
        "SCHEDULED",
        "PUBLISHED",
        "UNPUBLISHED",
        "ARCHIVED",
    ]
    assert publication.status == Publication.Status.DRAFT
    assert publication.published_at is None
    assert publication.body_text == (
        "Регламент VPN Подключайтесь безопасно. Инструкция Один пункт Важная цитата"
    )

    publication.body = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Новый текст"}]}],
    }
    publication.save(update_fields=["body"])
    publication.refresh_from_db()

    assert publication.body_text == "Новый текст"

    publication.body = {
        "type": "doc",
        "content": [{"type": "html", "attrs": {"html": "<script />"}}],
    }
    with pytest.raises(ValidationError):
        publication.save(update_fields=["body"])
    publication.refresh_from_db()
    assert publication.body_text == "Новый текст"


@pytest.mark.parametrize(
    "document",
    [
        {"type": "doc", "content": [{"type": "html", "attrs": {"html": "<script />"}}]},
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "unsafe",
                            "marks": [{"type": "link", "attrs": {"href": "javascript:alert(1)"}}],
                        }
                    ],
                }
            ],
        },
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "malformed target",
                            "marks": [
                                {
                                    "type": "link",
                                    "attrs": {
                                        "href": "https://example.invalid",
                                        "target": {"not": "a string"},
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "malformed URL",
                            "marks": [{"type": "link", "attrs": {"href": "https://[invalid"}}],
                        }
                    ],
                }
            ],
        },
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "unsafe target",
                            "marks": [
                                {
                                    "type": "link",
                                    "attrs": {
                                        "href": "https://example.invalid",
                                        "target": "_blank",
                                        "rel": None,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        {
            "type": "doc",
            "content": [{"type": "heading", "attrs": {"level": 1}, "content": []}],
        },
    ],
)
def test_rich_text_rejects_unknown_nodes_unsafe_links_and_unapproved_headings(document):
    with pytest.raises(ValidationError):
        validate_rich_text_document(document)


def test_rich_text_normalizes_unicode_and_whitespace():
    document = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Ａ  Б\nВ"}],
            }
        ],
    }

    assert rich_text_to_plain_text(document) == "A Б В"


@pytest.mark.django_db
def test_publication_status_and_publish_date_are_consistent_in_database():
    publication = create_publication()

    publication.status = Publication.Status.PUBLISHED
    with pytest.raises(IntegrityError), transaction.atomic():
        publication.save(update_fields=["status"])

    publication.refresh_from_db()
    publication.published_at = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        publication.save(update_fields=["published_at"])

    publication.refresh_from_db()
    publication.status = Publication.Status.PUBLISHED
    publication.published_at = timezone.now()
    publication.save(update_fields=["status", "published_at"])
    publication.refresh_from_db()
    assert publication.status == Publication.Status.PUBLISHED
    assert publication.published_at is not None


@pytest.mark.django_db
def test_audience_service_stores_union_targets_and_all_is_exclusive():
    publication = create_publication()
    unit = OrgUnit.objects.create(external_id="engineering", name="Разработка")
    employee = create_user("employee-1")

    rules = replace_audience_rules(
        publication,
        org_units=[unit, unit],
        employees=[employee, employee],
        module_roles=["editor", " editor "],
    )

    assert {rule.kind for rule in rules} == {
        AudienceRule.Kind.ORG_UNIT,
        AudienceRule.Kind.EMPLOYEE,
        AudienceRule.Kind.MODULE_ROLE,
    }
    assert AudienceRule.objects.get(kind=AudienceRule.Kind.ORG_UNIT).org_unit.external_id == (
        "engineering"
    )
    assert AudienceRule.objects.get(kind=AudienceRule.Kind.EMPLOYEE).employee.portal_id == (
        "employee-1"
    )
    assert AudienceRule.objects.get(kind=AudienceRule.Kind.MODULE_ROLE).module_role == "editor"

    with pytest.raises(ValidationError, match="cannot be combined"):
        replace_audience_rules(publication, everyone=True, module_roles=["editor"])
    assert AudienceRule.objects.count() == 3

    all_rules = replace_audience_rules(publication, everyone=True)
    assert [rule.kind for rule in all_rules] == [AudienceRule.Kind.ALL]
    assert AudienceRule.objects.count() == 1


@pytest.mark.django_db
def test_audience_service_rejects_inactive_targets_without_losing_existing_rules():
    publication = create_publication()
    replace_audience_rules(publication, everyone=True)
    inactive_unit = OrgUnit.objects.create(
        external_id="closed",
        name="Закрытое подразделение",
        is_active=False,
    )
    inactive_user = create_user("blocked-1", active=False)

    with pytest.raises(ValidationError, match="Inactive organization"):
        replace_audience_rules(publication, org_units=[inactive_unit])
    with pytest.raises(ValidationError, match="Inactive employees"):
        replace_audience_rules(publication, employees=[inactive_user])

    assert list(AudienceRule.objects.values_list("kind", flat=True)) == [AudienceRule.Kind.ALL]


@pytest.mark.django_db
def test_audience_target_shape_and_duplicates_are_database_constraints():
    publication = create_publication()

    with pytest.raises(IntegrityError), transaction.atomic():
        AudienceRule.objects.create(
            publication=publication,
            kind=AudienceRule.Kind.ALL,
            module_role="editor",
        )

    AudienceRule.objects.create(publication=publication, kind=AudienceRule.Kind.ALL)
    with pytest.raises(IntegrityError), transaction.atomic():
        AudienceRule.objects.create(publication=publication, kind=AudienceRule.Kind.ALL)


@pytest.mark.django_db
def test_publication_view_service_is_idempotent_and_preserves_first_view():
    publication = create_publication()
    viewer = create_user("viewer-1")
    first = timezone.now() - timedelta(minutes=5)
    second = timezone.now()

    first_view = record_publication_view(publication, viewer, viewed_at=first)
    second_view = record_publication_view(publication, viewer, viewed_at=second)

    assert first_view.pk == second_view.pk
    assert PublicationView.objects.count() == 1
    second_view.refresh_from_db()
    assert second_view.first_viewed_at == first
    assert second_view.last_viewed_at == second

    with pytest.raises(IntegrityError), transaction.atomic():
        PublicationView.objects.create(
            publication=publication,
            user=viewer,
            first_viewed_at=second,
            last_viewed_at=second,
        )


@pytest.mark.django_db
def test_visible_to_enforces_publication_state_and_active_portal_identity():
    active = create_user("active")
    blocked = create_user("blocked", active=False)
    draft = create_publication()
    published = publish(
        Publication.objects.create(
            title="Published",
            slug="published",
            summary="Summary",
            body=rich_body(),
            category=draft.category,
            author=draft.author,
        )
    )
    replace_audience_rules(draft, everyone=True)
    replace_audience_rules(published, everyone=True)

    assert list(Publication.objects.visible_to(active)) == [published]
    assert not Publication.objects.visible_to(blocked).exists()
    assert not Publication.objects.visible_to(None).exists()


@pytest.mark.django_db
def test_visible_to_supports_all_employee_org_unit_and_module_role_union():
    engineering = OrgUnit.objects.create(external_id="engineering", name="Engineering")
    finance = OrgUnit.objects.create(external_id="finance", name="Finance")
    engineer = create_user("engineer")
    engineer.org_unit = engineering
    engineer.module_roles = ["editor"]
    engineer.save(update_fields=["org_unit", "module_roles"])
    grant_legacy_roles(engineer, ["editor"])
    finance_user = create_user("finance")
    finance_user.org_unit = finance
    finance_user.save(update_fields=["org_unit"])
    category = Category.objects.create(slug="audience", name="Audience")
    author = create_user("audience-author")

    def publication(slug: str) -> Publication:
        return publish(
            Publication.objects.create(
                title=slug,
                slug=slug,
                summary=slug,
                body=rich_body(),
                category=category,
                author=author,
            )
        )

    everyone = publication("everyone")
    employee = publication("employee")
    org = publication("org")
    role = publication("role")
    replace_audience_rules(everyone, everyone=True)
    replace_audience_rules(employee, employees=[engineer])
    replace_audience_rules(org, org_units=[engineering])
    replace_audience_rules(role, module_roles=["editor"])

    assert set(Publication.objects.visible_to(engineer)) == {everyone, employee, org, role}
    assert set(Publication.objects.visible_to(finance_user)) == {everyone}

    engineering.is_active = False
    engineering.save(update_fields=["is_active"])
    engineer.module_roles = []
    engineer.save(update_fields=["module_roles"])
    AccessGrant.objects.filter(user=engineer, module="NEWS", role="EDITOR").delete()
    assert set(Publication.objects.visible_to(engineer)) == {everyone, employee}
