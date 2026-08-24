import time
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.identity.managers import UserManager
from apps.identity.models import User
from apps.identity.services import grant_legacy_roles
from apps.organization.models import OrgUnit
from apps.publications import services as publication_services
from apps.publications.media import (
    _detected_mime,
    _image_dimensions,
    create_media_asset,
    delete_media_asset,
)
from apps.publications.models import (
    AudienceRule,
    AuditEvent,
    Category,
    MediaAsset,
    MediaUsage,
    Publication,
    PublicationPin,
    PublicationVersion,
    Tag,
)
from apps.publications.rich_text import (
    empty_rich_text_document,
    rich_text_asset_ids,
    rich_text_to_plain_text,
    validate_rich_text_document,
)
from apps.publications.services import (
    StaleRevisionError,
    create_publication,
    duplicate_publication,
    pin_publication,
    reconcile_publications,
    replace_audience_rules,
    transition_publication,
    unpin_publication,
    update_publication,
)
from apps.publications.tasks import reconcile_publications_task


def body(text: str = "Текст публикации") -> dict[str, object]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def audience_all() -> dict[str, object]:
    return {
        "everyone": True,
        "org_units": [],
        "org_unit_subtrees": [],
        "employees": [],
        "module_roles": [],
        "position_groups": [],
    }


@pytest.fixture
def stage4_domain():
    users: UserManager = User.objects  # pyright: ignore[reportAssignmentType]
    root = OrgUnit.objects.create(external_id="root", name="Company", kind="company")
    branch = OrgUnit.objects.create(external_id="branch", name="Branch", kind="branch", parent=root)
    department = OrgUnit.objects.create(
        external_id="department", name="Department", kind="department", parent=branch
    )
    author = users.create_user(
        portal_id="stage4-author",
        full_name="Author",
        module_roles=["author"],
        org_unit=branch,
    )
    editor = users.create_user(
        portal_id="stage4-editor",
        full_name="Editor",
        module_roles=["editor"],
        org_unit=branch,
    )
    employee = users.create_user(
        portal_id="stage4-employee",
        full_name="Employee",
        module_roles=["employee"],
        org_unit=department,
        position_group_external_id="engineers",
        position_group_name="Engineers",
    )
    outsider = users.create_user(
        portal_id="stage4-outsider",
        full_name="Outsider",
        module_roles=["employee"],
        org_unit=root,
    )
    grant_legacy_roles(author, ["author"])
    grant_legacy_roles(editor, ["editor"])
    grant_legacy_roles(employee, ["employee"])
    grant_legacy_roles(outsider, ["employee"])
    category = Category.objects.create(slug="stage4", name="Stage 4")
    return author, editor, employee, outsider, category, root, branch, department


def make_publication(actor: User, category: Category, **extra) -> Publication:
    data: dict[str, object] = {
        "title": "Stage 4 publication",
        "summary": "Editorial workflow",
        "body": body(),
        "category": category,
        "audience": audience_all(),
    }
    data.update(extra)
    return create_publication(actor=actor, data=data)


@pytest.mark.django_db
def test_full_lifecycle_scheduler_and_immutable_versions(stage4_domain):
    author, editor, *_rest, category, _root, _branch, _department = stage4_domain
    publication = make_publication(author, category)
    assert publication.edit_revision == 1
    publication = transition_publication(publication, action="submit-review", actor=author)
    assert publication.status == Publication.Status.IN_REVIEW
    publication = transition_publication(publication, action="return-to-draft", actor=editor)
    scheduled = timezone.now() + timedelta(minutes=2)
    publication = transition_publication(
        publication,
        action="schedule",
        actor=editor,
        scheduled_for=scheduled,
        expires_at=scheduled + timedelta(hours=1),
    )
    assert publication.status == Publication.Status.SCHEDULED
    publication = transition_publication(
        publication,
        action="schedule",
        actor=editor,
        scheduled_for=scheduled + timedelta(minutes=1),
    )
    publication = transition_publication(publication, action="cancel-schedule", actor=editor)
    publication = transition_publication(publication, action="publish", actor=editor)
    publication = transition_publication(publication, action="unpublish", actor=editor)
    publication = transition_publication(publication, action="archive", actor=editor)
    assert publication.status == Publication.Status.ARCHIVED
    with pytest.raises(ValidationError, match="not allowed"):
        transition_publication(publication, action="publish", actor=editor)
    versions = PublicationVersion.objects.filter(publication=publication)
    assert versions.count() == 9
    version = versions.first()
    assert version is not None and len(version.content_hash) == 64
    with pytest.raises(ValidationError, match="append-only"):
        PublicationVersion.objects.update(reason="tampered")
    with pytest.raises(ValidationError, match="append-only"):
        version.delete()
    events = list(AuditEvent.objects.filter(publication=publication))
    assert [event.event_type for event in events] == [
        AuditEvent.Type.CREATED,
        AuditEvent.Type.SUBMITTED_FOR_REVIEW,
        AuditEvent.Type.RETURNED_TO_DRAFT,
        AuditEvent.Type.SCHEDULED,
        AuditEvent.Type.SCHEDULED,
        AuditEvent.Type.SCHEDULE_CANCELLED,
        AuditEvent.Type.PUBLISHED,
        AuditEvent.Type.UNPUBLISHED,
        AuditEvent.Type.ARCHIVED,
    ]
    assert all(
        event.target_type == AuditEvent.TargetType.PUBLICATION
        and event.target_id == str(publication.pk)
        and event.actor.pk in {author.pk, editor.pk}
        for event in events
    )
    assert events[0].previous_state == {}
    assert events[0].new_state["status"] == Publication.Status.DRAFT
    assert events[-1].previous_state["status"] == Publication.Status.UNPUBLISHED
    assert events[-1].new_state["status"] == Publication.Status.ARCHIVED


@pytest.mark.django_db
def test_revision_conflicts_autosave_coalescing_and_permissions(stage4_domain):
    author, editor, employee, _outsider, category, _root, _branch, _department = stage4_domain
    publication = make_publication(author, category)
    publication = update_publication(
        publication,
        actor=author,
        expected_revision=1,
        autosave=True,
        data={"title": "Autosaved once"},
    )
    publication = update_publication(
        publication,
        actor=author,
        expected_revision=2,
        autosave=True,
        data={"summary": "Autosaved twice"},
    )
    assert publication.edit_revision == 3
    assert publication.last_autosaved_at is not None
    assert (
        PublicationVersion.objects.filter(publication=publication, reason="autosave").count() == 1
    )
    with pytest.raises(StaleRevisionError) as stale:
        update_publication(
            publication,
            actor=author,
            expected_revision=1,
            data={"title": "Lost update"},
        )
    assert stale.value.current_revision == 3
    with pytest.raises(PermissionDenied):
        update_publication(
            publication,
            actor=employee,
            expected_revision=3,
            data={"title": "IDOR"},
        )
    with pytest.raises(PermissionDenied):
        transition_publication(publication, action="publish", actor=author)
    published = transition_publication(publication, action="publish", actor=editor)
    changed = update_publication(
        published,
        actor=editor,
        expected_revision=published.edit_revision,
        data={"title": "Editor can correct published material"},
    )
    assert changed.title.startswith("Editor can")


@pytest.mark.django_db
def test_subtree_position_group_exact_and_named_audience(stage4_domain):
    author, editor, employee, outsider, category, root, branch, department = stage4_domain
    publications = [
        make_publication(author, category, title=f"Audience {index}") for index in range(4)
    ]
    replace_audience_rules(publications[0], org_units=[department])
    replace_audience_rules(publications[1], org_unit_subtrees=[branch])
    replace_audience_rules(
        publications[2],
        position_groups=[{"external_id": "engineers", "name": "Engineers"}],
    )
    replace_audience_rules(publications[3], employees=[employee])
    for publication in publications:
        transition_publication(publication, action="publish", actor=editor)
    assert Publication.objects.visible_to(employee).count() == 4
    assert not Publication.objects.visible_to(outsider).exists()
    assert AudienceRule.objects.filter(include_descendants=True, org_unit=branch).exists()
    with pytest.raises(ValidationError, match="ALL"):
        replace_audience_rules(publications[0], everyone=True, org_units=[root])


@pytest.mark.django_db
def test_inactive_subtree_ancestor_is_not_visible(stage4_domain):
    author, editor, employee, _outsider, category, _root, branch, _department = stage4_domain
    publication = make_publication(author, category)
    replace_audience_rules(publication, org_unit_subtrees=[branch])
    transition_publication(publication, action="publish", actor=editor)
    assert Publication.objects.visible_to(employee).filter(pk=publication.pk).exists()

    branch.is_active = False
    branch.save(update_fields=["is_active"])
    assert not Publication.objects.visible_to(employee).filter(pk=publication.pk).exists()


@pytest.mark.django_db
def test_pins_feed_exclusion_limits_and_automatic_cleanup(stage4_domain):
    author, editor, employee, _outsider, category, _root, _branch, _department = stage4_domain
    publications = [
        make_publication(author, category, title=f"Pinned {index}") for index in range(6)
    ]
    for publication in publications:
        transition_publication(publication, action="publish", actor=editor)
    for slot, publication in enumerate(publications[:5], start=1):
        pin_publication(publication, actor=editor, slot=slot)
    assert list(PublicationPin.objects.values_list("slot", flat=True)) == [1, 2, 3, 4, 5]
    with pytest.raises(ValidationError, match="occupied"):
        pin_publication(publications[5], actor=editor, slot=5)
    regular = Publication.objects.visible_to(employee).filter(pin__isnull=True)
    assert list(regular) == [publications[5]]
    transition_publication(publications[0], action="unpublish", actor=editor)
    assert not PublicationPin.objects.filter(publication=publications[0]).exists()
    unpin_publication(publications[1], actor=editor)
    assert PublicationPin.objects.count() == 3


@pytest.mark.django_db
def test_duplicate_copies_editorial_material_but_not_state_or_pin(stage4_domain):
    author, editor, _employee, _outsider, category, _root, _branch, _department = stage4_domain
    tag = Tag.objects.create(slug="important", name="Important")
    source = make_publication(author, category, tags=[tag])
    source = transition_publication(source, action="publish", actor=editor)
    pin_publication(source, actor=editor, slot=1)
    clone = duplicate_publication(source, actor=editor)
    assert clone.status == Publication.Status.DRAFT
    assert clone.author == editor
    assert list(clone.tags.all()) == [tag]
    assert clone.audience_rules.count() == source.audience_rules.count()
    assert not PublicationPin.objects.filter(publication=clone).exists()
    assert clone.published_at is clone.scheduled_for is clone.archived_at is None
    assert AuditEvent.objects.filter(
        publication=clone, event_type="publication.duplicated"
    ).exists()


def png_upload(name: str = "pixel.png", content_type: str = "image/png"):
    stream = BytesIO()
    Image.new("RGB", (3, 2), "red").save(stream, format="PNG")
    return SimpleUploadedFile(name, stream.getvalue(), content_type=content_type)


@pytest.mark.django_db
def test_media_upload_validation_reuse_and_delete(stage4_domain, tmp_path):
    author, editor, _employee, _outsider, category, _root, _branch, _department = stage4_domain
    with override_settings(MEDIA_ROOT=tmp_path):
        asset = create_media_asset(upload=png_upload("../unsafe.png"), actor=author)
        assert asset.original_name == "unsafe.png"
        assert asset.storage_key.startswith("assets/")
        assert asset.width == 3 and asset.height == 2
        first = make_publication(author, category, body_assets=[asset])
        second = make_publication(author, category, body_assets=[asset], title="Reuse")
        assert MediaUsage.objects.filter(asset=asset).count() == 2
        with pytest.raises(ValidationError, match="used"):
            delete_media_asset(asset, actor=editor)
        MediaUsage.objects.filter(publication__in=[first, second]).delete()
        delete_media_asset(asset, actor=editor)
        assert not MediaAsset.objects.filter(pk=asset.pk).exists()
        deleted = AuditEvent.objects.get(
            target_type=AuditEvent.TargetType.MEDIA,
            target_id=str(asset.pk),
            event_type=AuditEvent.Type.MEDIA_DELETED,
        )
        assert deleted.previous_state["original_name"] == "unsafe.png"
        assert deleted.new_state == {}


@pytest.mark.django_db
def test_media_upload_failure_removes_file(stage4_domain, tmp_path, monkeypatch):
    author = stage4_domain[0]

    def fail_save(*_args, **_kwargs):
        raise IntegrityError("forced commit failure")

    monkeypatch.setattr(MediaAsset, "save", fail_save)
    with override_settings(MEDIA_ROOT=tmp_path), pytest.raises(IntegrityError):
        create_media_asset(upload=png_upload(), actor=author)
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    assert not MediaAsset.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_media_delete_rollback_keeps_database_and_file(stage4_domain, tmp_path):
    author, editor, *_rest = stage4_domain
    with override_settings(MEDIA_ROOT=tmp_path):
        asset = create_media_asset(upload=png_upload(), actor=author)
        stored_path = asset.file.path
        with pytest.raises(RuntimeError, match="rollback"), transaction.atomic():
            delete_media_asset(asset, actor=editor)
            raise RuntimeError("rollback")
        assert MediaAsset.objects.filter(pk=asset.pk).exists()
        assert stored_path and Path(stored_path).is_file()
        assert not AuditEvent.objects.filter(
            target_type=AuditEvent.TargetType.MEDIA,
            target_id=str(asset.pk),
            event_type=AuditEvent.Type.MEDIA_DELETED,
        ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "content", "content_type"),
    [
        ("payload.svg", b"<svg onload='alert(1)'></svg>", "image/svg+xml"),
        ("photo.png", b"<html><script>alert(1)</script>", "image/png"),
        ("program.exe", b"MZ" + b"x" * 20, "application/octet-stream"),
        ("photo.png", b"%PDF-1.7", "application/pdf"),
    ],
)
def test_media_rejects_unsafe_extensions_mime_and_content(
    stage4_domain, tmp_path, name, content, content_type
):
    author = stage4_domain[0]
    upload = SimpleUploadedFile(name, content, content_type=content_type)
    with override_settings(MEDIA_ROOT=tmp_path), pytest.raises(ValidationError):
        create_media_asset(upload=upload, actor=author)


@pytest.mark.django_db
def test_media_content_endpoint_hides_idor_and_uses_accel(stage4_domain, tmp_path):
    _author, editor, employee, outsider, category, *_units = stage4_domain
    client = APIClient()
    with override_settings(MEDIA_ROOT=tmp_path):
        asset = create_media_asset(upload=png_upload(), actor=editor)
        publication = make_publication(editor, category, body_assets=[asset])
        replace_audience_rules(publication, employees=[employee])
        transition_publication(publication, action="publish", actor=editor)
        client.force_authenticate(editor)
        editor_response = client.get(f"/api/v1/media/{asset.pk}/content")
        assert editor_response.status_code == 200
        assert editor_response["X-Accel-Redirect"] == f"/_protected_media/{asset.storage_key}"
        client.force_authenticate(employee)
        assert client.get(f"/api/v1/media/{asset.pk}/content").status_code == 200
        client.force_authenticate(outsider)
        assert client.get(f"/api/v1/media/{asset.pk}/content").status_code == 404
        assert client.get("/_protected_media/assets/anything.png").status_code == 404


@pytest.mark.django_db
def test_stage4_api_conflict_taxonomy_versions_and_transitions(stage4_domain):
    _author, editor, _employee, _outsider, category, _root, _branch, _department = stage4_domain
    client = APIClient()
    client.force_authenticate(editor)
    payload = {
        "title": "API lifecycle",
        "summary": "API coverage",
        "body": body(),
        "category": category.slug,
        "audience": audience_all(),
    }
    created = client.post("/api/v1/editorial/publications", payload, format="json")
    assert created.status_code == 201
    publication_id = created.data["id"]
    missing = client.patch(
        f"/api/v1/editorial/publications/{publication_id}", {"title": "Missing"}, format="json"
    )
    assert missing.status_code == 400
    updated = client.patch(
        f"/api/v1/editorial/publications/{publication_id}",
        {"title": "Updated", "expected_revision": created.data["edit_revision"]},
        format="json",
    )
    assert updated.status_code == 200
    stale = client.patch(
        f"/api/v1/editorial/publications/{publication_id}",
        {"title": "Stale", "expected_revision": created.data["edit_revision"]},
        format="json",
    )
    assert stale.status_code == 409
    assert stale.data["error"]["current_revision"] == updated.data["edit_revision"]
    review = client.post(
        f"/api/v1/editorial/publications/{publication_id}/submit-review",
        {"expected_revision": updated.data["edit_revision"]},
        format="json",
    )
    assert review.data["status"] == "IN_REVIEW"
    assert client.get("/api/v1/editorial/review").data["results"][0]["id"] == publication_id
    versions = client.get(f"/api/v1/editorial/publications/{publication_id}/versions")
    assert versions.status_code == 200 and len(versions.data) >= 3
    version_number = versions.data[0]["version_number"]
    assert (
        client.get(
            f"/api/v1/editorial/publications/{publication_id}/versions/{version_number}"
        ).status_code
        == 200
    )
    new_category = client.post(
        "/api/v1/editorial/categories",
        {"slug": "new-category", "name": "New", "sort_order": 3},
        format="json",
    )
    assert new_category.status_code == 201
    tag = client.post(
        "/api/v1/editorial/tags", {"slug": "new-tag", "name": "New tag"}, format="json"
    )
    assert tag.status_code == 201
    assert (
        client.patch(
            f"/api/v1/editorial/tags/{tag.data['id']}", {"is_active": False}, format="json"
        ).data["is_active"]
        is False
    )
    category_event = AuditEvent.objects.get(
        event_type=AuditEvent.Type.CATEGORY_CREATED,
        target_type=AuditEvent.TargetType.CATEGORY,
        target_id=str(new_category.data["id"]),
    )
    assert category_event.previous_state == {}
    assert category_event.new_state["name"] == "New"
    tag_events = list(
        AuditEvent.objects.filter(
            target_type=AuditEvent.TargetType.TAG,
            target_id=str(tag.data["id"]),
        )
    )
    assert [event.event_type for event in tag_events] == [
        AuditEvent.Type.TAG_CREATED,
        AuditEvent.Type.TAG_UPDATED,
    ]
    assert tag_events[1].previous_state["is_active"] is True
    assert tag_events[1].new_state["is_active"] is False


@pytest.mark.django_db
def test_position_group_audience_uses_portal_id_and_canonical_name(stage4_domain):
    _author, editor, *_rest, category, _root, _branch, _department = stage4_domain
    client = APIClient()
    client.force_authenticate(editor)
    payload = {
        "title": "Canonical position group",
        "summary": "Portal owns the display name",
        "body": body(),
        "category": category.slug,
        "audience": {
            "everyone": False,
            "org_units": [],
            "org_unit_subtrees": [],
            "employees": [],
            "module_roles": [],
            "position_groups": [{"external_id": "specialists", "name": "Forged local label"}],
        },
    }
    created = client.post("/api/v1/editorial/publications", payload, format="json")
    assert created.status_code == 201
    assert created.data["audience"]["position_groups"] == [
        {"external_id": "specialists", "name": "Специалисты"}
    ]

    payload["audience"]["position_groups"] = [{"external_id": "retired", "name": "Inactive"}]
    rejected = client.post("/api/v1/editorial/publications", payload, format="json")
    assert rejected.status_code == 400
    assert "inactive" in str(rejected.data).lower()


@pytest.mark.django_db
def test_scheduler_reconcile_is_idempotent_and_expires(stage4_domain):
    author, editor, _employee, _outsider, category, _root, _branch, _department = stage4_domain
    publication = make_publication(author, category)
    scheduled = timezone.now() + timedelta(seconds=30)
    publication = transition_publication(
        publication,
        action="schedule",
        actor=editor,
        scheduled_for=scheduled,
        expires_at=scheduled + timedelta(seconds=30),
    )
    assert reconcile_publications(now=scheduled - timedelta(seconds=1))["published"] == 0
    assert reconcile_publications(now=scheduled + timedelta(seconds=1))["published"] == 1
    assert reconcile_publications(now=scheduled + timedelta(seconds=2))["published"] == 0
    assert reconcile_publications(now=scheduled + timedelta(seconds=31))["expired"] == 1
    publication.refresh_from_db()
    assert publication.status == Publication.Status.UNPUBLISHED
    task = cast(Any, reconcile_publications_task)
    cache.delete("tandem:celery:reconcile-heartbeat")
    result = task.apply().get()
    assert result == {"published": 0, "expired": 0}
    heartbeat = cache.get("tandem:celery:reconcile-heartbeat")
    assert heartbeat is not None and 0 <= time.time() - heartbeat < 5


@pytest.mark.django_db
def test_rich_text_table_and_internal_media_contract(stage4_domain):
    asset_id = "11111111-1111-1111-1111-111111111111"
    document = {
        "type": "doc",
        "content": [
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableHeader",
                                "attrs": {"colspan": 1, "rowspan": 1, "colwidth": None},
                                "content": [{"type": "paragraph", "content": []}],
                            }
                        ],
                    }
                ],
            },
            {"type": "assetImage", "attrs": {"asset_id": asset_id}},
            {"type": "internalVideo", "attrs": {"asset_id": asset_id}},
            {"type": "attachment", "attrs": {"asset_id": asset_id}},
        ],
    }
    validate_rich_text_document(document)
    assert rich_text_asset_ids(document) == {UUID(asset_id)}
    with pytest.raises(ValidationError):
        validate_rich_text_document(
            {"type": "doc", "content": [{"type": "assetImage", "attrs": {"src": "https://x"}}]}
        )


@pytest.mark.django_db
def test_media_upload_list_delete_api_and_editorial_errors(stage4_domain, tmp_path):
    author, editor, _employee, _outsider, _category, _root, _branch, _department = stage4_domain
    client = APIClient()
    client.force_authenticate(editor)
    with override_settings(MEDIA_ROOT=tmp_path):
        assert client.post("/api/v1/editorial/media", {}, format="multipart").status_code == 400
        invalid = SimpleUploadedFile("bad.png", b"not an image", content_type="image/png")
        assert (
            client.post(
                "/api/v1/editorial/media", {"file": invalid}, format="multipart"
            ).status_code
            == 400
        )
        uploaded = client.post(
            "/api/v1/editorial/media", {"file": png_upload()}, format="multipart"
        )
        assert uploaded.status_code == 201
        asset_id = uploaded.data["id"]
        uploaded_event = AuditEvent.objects.get(
            event_type=AuditEvent.Type.MEDIA_UPLOADED,
            target_type=AuditEvent.TargetType.MEDIA,
            target_id=asset_id,
        )
        assert uploaded_event.new_state["original_name"] == "pixel.png"
        listing = client.get("/api/v1/editorial/media")
        assert listing.data["results"][0]["id"] == asset_id
        client.force_authenticate(author)
        assert client.delete(f"/api/v1/editorial/media/{asset_id}").status_code == 400
        client.force_authenticate(editor)
        assert client.delete(f"/api/v1/editorial/media/{asset_id}").status_code == 204
        deleted_event = AuditEvent.objects.get(
            event_type=AuditEvent.Type.MEDIA_DELETED,
            target_type=AuditEvent.TargetType.MEDIA,
            target_id=asset_id,
        )
        assert deleted_event.previous_state["original_name"] == "pixel.png"
    assert client.get("/api/v1/editorial/publications?status=UNKNOWN").status_code == 400


@pytest.mark.django_db
def test_pin_and_duplicate_http_endpoints(stage4_domain):
    author, editor, employee, _outsider, category, _root, _branch, _department = stage4_domain
    publication = make_publication(author, category)
    publication = transition_publication(publication, action="publish", actor=editor)
    client = APIClient()
    client.force_authenticate(editor)
    pin = client.put(f"/api/v1/news/{publication.pk}/pin", {"slot": 1}, format="json")
    assert pin.status_code == 200 and pin.data["slot"] == 1
    client.force_authenticate(employee)
    pinned = client.get("/api/v1/news/pinned")
    assert pinned.status_code == 200 and pinned.data[0]["id"] == str(publication.pk)
    assert client.get("/api/v1/news").data["results"] == []
    client.force_authenticate(editor)
    duplicated = client.post(f"/api/v1/editorial/publications/{publication.pk}/duplicate")
    assert duplicated.status_code == 201 and duplicated.data["status"] == "DRAFT"
    assert client.delete(f"/api/v1/news/{publication.pk}/pin").status_code == 204
    assert (
        client.put(f"/api/v1/news/{publication.pk}/pin", {"slot": 0}, format="json").status_code
        == 400
    )


@pytest.mark.django_db
def test_concurrent_pin_conflict_is_a_validation_response(stage4_domain, monkeypatch):
    author, editor, *_rest, category, _root, _branch, _department = stage4_domain
    publication = transition_publication(
        make_publication(author, category), action="publish", actor=editor
    )

    def collide(*_args, **_kwargs):
        raise IntegrityError("publication_pin_slot_key")

    monkeypatch.setattr(publication_services.PublicationPin.objects, "update_or_create", collide)
    client = APIClient()
    client.force_authenticate(editor)
    response = client.put(f"/api/v1/news/{publication.pk}/pin", {"slot": 1}, format="json")
    assert response.status_code == 400
    assert "occupied" in str(response.data).lower()


@pytest.mark.django_db
def test_rich_text_media_nodes_require_compatible_kinds(stage4_domain, tmp_path):
    _author, editor, *_rest, category, _root, _branch, _department = stage4_domain
    client = APIClient()
    client.force_authenticate(editor)
    with override_settings(MEDIA_ROOT=tmp_path):
        image = create_media_asset(upload=png_upload(), actor=editor)
        document = create_media_asset(
            upload=SimpleUploadedFile("policy.pdf", b"%PDF-1.7\n", content_type="application/pdf"),
            actor=editor,
        )
        payload = {
            "title": "Media node contract",
            "summary": "Kinds are enforced",
            "category": category.slug,
            "audience": audience_all(),
        }
        for node_type, asset in (("internalVideo", image), ("assetImage", document)):
            response = client.post(
                "/api/v1/editorial/publications",
                {
                    **payload,
                    "body": {
                        "type": "doc",
                        "content": [{"type": node_type, "attrs": {"asset_id": str(asset.pk)}}],
                    },
                },
                format="json",
            )
            assert response.status_code == 400
            assert "incompatible" in str(response.data).lower()
        attachment = client.post(
            "/api/v1/editorial/publications",
            {
                **payload,
                "body": {
                    "type": "doc",
                    "content": [{"type": "attachment", "attrs": {"asset_id": str(document.pk)}}],
                },
            },
            format="json",
        )
        assert attachment.status_code == 201


@pytest.mark.django_db
def test_transition_http_errors_and_taxonomy_author_boundaries(stage4_domain):
    author, editor, _employee, _outsider, category, _root, _branch, _department = stage4_domain
    publication = make_publication(author, category)
    client = APIClient()
    client.force_authenticate(editor)
    past = timezone.now() - timedelta(seconds=1)
    path = f"/api/v1/editorial/publications/{publication.pk}/schedule"
    assert client.post(path, {"scheduled_for": past.isoformat()}, format="json").status_code == 400
    future = timezone.now() + timedelta(minutes=2)
    assert (
        client.post(
            path,
            {"scheduled_for": future.isoformat(), "expires_at": future.isoformat()},
            format="json",
        ).status_code
        == 400
    )
    scheduled = client.post(
        path,
        {
            "scheduled_for": future.isoformat(),
            "expires_at": (future + timedelta(hours=1)).isoformat(),
        },
        format="json",
    )
    assert scheduled.data["status"] == "SCHEDULED"
    cancelled = client.post(
        f"/api/v1/editorial/publications/{publication.pk}/cancel-schedule", format="json"
    )
    assert cancelled.data["status"] == "IN_REVIEW"
    client.force_authenticate(author)
    assert (
        client.post(
            "/api/v1/editorial/categories",
            {"slug": "denied", "name": "Denied"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/editorial/tags", {"slug": "denied", "name": "Denied"}, format="json"
        ).status_code
        == 400
    )
    client.force_authenticate(editor)
    patched = client.patch(
        f"/api/v1/editorial/categories/{category.pk}", {"is_active": False}, format="json"
    )
    assert patched.status_code == 200 and patched.data["is_active"] is False
    client.force_authenticate(author)
    assert (
        client.patch(
            f"/api/v1/editorial/categories/{category.pk}", {"is_active": True}, format="json"
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_service_validation_edge_cases(stage4_domain, tmp_path):
    author, editor, employee, _outsider, category, _root, branch, _department = stage4_domain
    publication = make_publication(author, category)
    inactive = Tag.objects.create(slug="inactive", name="Inactive", is_active=False)
    with pytest.raises(ValidationError, match="Inactive tags"):
        update_publication(
            publication,
            actor=author,
            expected_revision=1,
            data={"tags": [inactive]},
        )
    branch.is_active = False
    branch.save()
    with pytest.raises(ValidationError, match="Inactive organization"):
        replace_audience_rules(publication, org_units=[branch])
    employee.is_active = False
    employee.save()
    with pytest.raises(ValidationError, match="Inactive employees"):
        replace_audience_rules(publication, employees=[employee])
    with pytest.raises(ValidationError, match="Module role"):
        replace_audience_rules(publication, module_roles=["x" * 65])
    with pytest.raises(ValidationError, match="Position group"):
        replace_audience_rules(
            publication,
            position_groups=[{"external_id": "x" * 129, "name": "Too long"}],
        )
    with override_settings(MEDIA_ROOT=tmp_path):
        document = create_media_asset(
            upload=SimpleUploadedFile("file.pdf", b"%PDF-1.7\n", content_type="application/pdf"),
            actor=author,
        )
        with pytest.raises(ValidationError, match="Cover"):
            update_publication(
                publication,
                actor=author,
                expected_revision=publication.edit_revision,
                data={"cover": document},
            )
    with pytest.raises(PermissionDenied):
        pin_publication(publication, actor=author, slot=1)
    with pytest.raises(ValidationError, match="published"):
        pin_publication(publication, actor=editor, slot=1)
    published = transition_publication(publication, action="publish", actor=editor)
    with pytest.raises(ValidationError, match="slot"):
        pin_publication(published, actor=editor, slot=6)
    with pytest.raises(PermissionDenied):
        unpin_publication(published, actor=author)


def test_media_signature_detection_and_invalid_images():
    assert _detected_mime(b"\xff\xd8\xffrest", ".jpg") == "image/jpeg"
    assert _detected_mime(b"GIF89arest", ".gif") == "image/gif"
    assert _detected_mime(b"RIFFxxxxWEBPrest", ".webp") == "image/webp"
    assert _detected_mime(b"xxxxftypisom", ".mp4") == "video/mp4"
    assert _detected_mime(b"%PDF-1.7", ".pdf") == "application/pdf"
    assert _detected_mime(b"PK\x03\x04broken", ".docx") is None
    assert _detected_mime(b"unknown", ".bin") is None
    with pytest.raises(ValidationError, match="invalid"):
        _image_dimensions(b"not an image")


@pytest.mark.parametrize(
    "document",
    [
        {"type": "doc", "content": [1]},
        {"type": "doc", "content": "not-a-list"},
        {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "attrs": {"start": 0},
                    "content": [],
                }
            ],
        },
        {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "attrs": "wrong",
                    "content": [],
                }
            ],
        },
        {"type": "doc", "content": [{"type": "assetImage", "attrs": {"asset_id": 1}}]},
        {
            "type": "doc",
            "content": [{"type": "assetImage", "attrs": {"asset_id": "not-a-uuid"}}],
        },
        {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": 1}]}],
        },
        {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "x" * 100_001}]}
            ],
        },
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "x", "marks": {}}],
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
                            "text": "x",
                            "marks": [{"type": "bold"}, {"type": "bold"}],
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
                            "text": "x",
                            "marks": [
                                {
                                    "type": "link",
                                    "attrs": {"href": "https://example.test", "rel": "unsafe"},
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
                            "text": "x",
                            "marks": [
                                {
                                    "type": "link",
                                    "attrs": {"href": "https://example.test", "class": "evil"},
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    ],
)
def test_rich_text_rejects_bad_shapes_and_limits(document):
    with pytest.raises(ValidationError):
        validate_rich_text_document(document)


def test_rich_text_depth_node_limits_and_empty_document():
    assert empty_rich_text_document() == {"type": "doc", "content": []}
    nested: dict[str, object] = {"type": "paragraph", "content": []}
    for _ in range(18):
        nested = {"type": "blockquote", "content": [nested]}
    with pytest.raises(ValidationError, match="deeply"):
        validate_rich_text_document({"type": "doc", "content": [nested]})
    with pytest.raises(ValidationError, match="too many"):
        validate_rich_text_document(
            {
                "type": "doc",
                "content": [{"type": "paragraph", "content": []} for _ in range(5_001)],
            }
        )
    assert (
        rich_text_to_plain_text({"type": "doc", "content": [{"type": "paragraph", "content": []}]})
        == ""
    )
