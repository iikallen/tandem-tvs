"""Stage 4 acceptance against the configured PostgreSQL, Redis and Celery stack.

Run ``prepare`` before restarting backend/worker/beat, then ``verify``.  The
second phase observes both the scheduled publication and its automatic expiry.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.publications.models import Publication, PublicationPin, PublicationVersion  # noqa: E402

STATE_FILE = Path(settings.MEDIA_ROOT) / ".stage4-acceptance-started"
client = APIClient()


def request(portal_id: str, method: str, path: str, data=None):
    settings.MOCK_PORTAL_USER_ID = portal_id
    return getattr(client, method)(path, data, format="json", HTTP_HOST="localhost")


def rich_body(text: str):
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]},
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableCell",
                                "content": [{"type": "paragraph", "content": []}],
                            }
                        ],
                    }
                ],
            },
        ],
    }


def prepare() -> None:
    assert connection.vendor == "postgresql", "Stage 4 acceptance requires PostgreSQL"
    assert settings.CELERY_BROKER_URL.rstrip("/").endswith("/2")
    call_command("seed_stage2_demo", verbosity=0)
    call_command("seed_stage3_demo", verbosity=0)
    settings.MOCK_PORTAL_USER_ID = "editor-1"
    image = BytesIO()
    Image.new("RGB", (4, 4), "#5b3fd1").save(image, format="PNG")
    upload = client.post(
        "/api/v1/editorial/media",
        {"file": SimpleUploadedFile("stage4.png", image.getvalue(), "image/png")},
        format="multipart",
        HTTP_HOST="localhost",
    )
    assert upload.status_code == 201, upload.data
    asset_id = upload.data["id"]

    created = request(
        "author-1",
        "post",
        "/api/v1/editorial/publications",
        {
            "title": "Stage 4 scheduled acceptance",
            "summary": "Real PostgreSQL, Celery and restart acceptance",
            "body": {
                **rich_body("Stage 4 acceptance body"),
                "content": [
                    *rich_body("Stage 4 acceptance body")["content"],
                    {"type": "assetImage", "attrs": {"asset_id": asset_id}},
                ],
            },
            "category": "regulations",
            "cover": asset_id,
            "audience": {
                "everyone": False,
                "org_units": [],
                "org_unit_subtrees": ["communications"],
                "employees": [],
                "module_roles": [],
                "position_groups": [],
            },
        },
    )
    assert created.status_code == 201, created.data
    publication_id = created.data["id"]
    # The API owns UUID creation; retain ids across the restart in shared media storage.
    scheduled_for = timezone.now() + timedelta(seconds=25)
    expires_at = scheduled_for + timedelta(seconds=25)
    scheduled = request(
        "editor-1",
        "post",
        f"/api/v1/editorial/publications/{publication_id}/schedule",
        {
            "expected_revision": created.data["edit_revision"],
            "scheduled_for": scheduled_for.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
    )
    assert scheduled.status_code == 200, scheduled.data
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(
            {
                "publication": publication_id,
                "asset": asset_id,
                "scheduled_for": scheduled_for.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
        ),
        encoding="utf-8",
    )
    print({"result": "PREPARED", "publication": publication_id, "asset": asset_id})


def verify() -> None:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    publication_id = state["publication"]
    asset_id = state["asset"]
    scheduled_for = datetime.fromisoformat(state["scheduled_for"])
    expires_at = datetime.fromisoformat(state["expires_at"])
    deadline = expires_at + timedelta(seconds=60)
    while True:
        publication = Publication.objects.get(pk=publication_id)
        if publication.status == Publication.Status.UNPUBLISHED:
            break
        if timezone.now() >= deadline:
            raise AssertionError("Celery missed the 60-second publish/expiry SLA")
        time.sleep(2)

    publication = Publication.objects.get(pk=publication_id)
    assert publication.published_at is not None
    assert publication.unpublished_at is not None
    publish_delay = (publication.published_at - scheduled_for).total_seconds()
    unpublish_delay = (publication.unpublished_at - expires_at).total_seconds()
    assert 0 <= publish_delay <= 60, publish_delay
    assert 0 <= unpublish_delay <= 60, unpublish_delay
    assert PublicationVersion.objects.filter(publication=publication).count() >= 3
    assert request("employee-1", "get", f"/api/v1/news/{publication_id}").status_code == 404
    assert request("admin-1", "get", f"/api/v1/news/{publication_id}").status_code == 404
    editor_media = request("editor-1", "get", f"/api/v1/media/{asset_id}/content")
    assert editor_media.status_code == 200
    assert editor_media["X-Accel-Redirect"].startswith("/_protected_media/")
    assert request("employee-1", "get", f"/api/v1/media/{asset_id}/content").status_code == 404
    assert (
        Path(settings.MEDIA_ROOT)
        / editor_media["X-Accel-Redirect"].removeprefix("/_protected_media/")
    ).is_file()

    duplicate = request(
        "editor-1", "post", f"/api/v1/editorial/publications/{publication_id}/duplicate"
    )
    assert duplicate.status_code == 201, duplicate.data
    assert duplicate.data["status"] == "DRAFT"
    assert duplicate.data["scheduled_for"] is None
    assert duplicate.data["published_at"] is None
    assert not PublicationPin.objects.filter(publication_id=duplicate.data["id"]).exists()
    STATE_FILE.unlink(missing_ok=True)
    print(
        {
            "result": "PASS",
            "database": connection.vendor,
            "celery_redis_db": 2,
            "restart_persistence": "PASS",
            "scheduled_then_expired": "PASS",
            "publish_delay_seconds": round(publish_delay, 3),
            "unpublish_delay_seconds": round(unpublish_delay, 3),
            "outsider_after_expiry": 404,
            "immutable_versions": PublicationVersion.objects.filter(
                publication=publication
            ).count(),
            "duplicate_state": "DRAFT",
            "protected_media": "editor=200, outsider=404, persisted=PASS",
        }
    )


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "verify"
    {"prepare": prepare, "verify": verify}[phase]()
