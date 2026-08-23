"""Run the destructive-demo Stage 2 vertical-slice acceptance against configured PostgreSQL."""

import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.identity.models import User  # noqa: E402
from apps.publications.models import Category, Publication, PublicationView  # noqa: E402
from apps.publications.services import replace_audience_rules  # noqa: E402

client = APIClient()


def request(portal_id: str, method: str, path: str, data=None):
    settings.MOCK_PORTAL_USER_ID = portal_id
    response = getattr(client, method)(path, data, format="json", HTTP_HOST="localhost")
    return response


def body(text: str):
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def create_and_publish(title: str, audience: dict[str, object]):
    created = request(
        "editor-1",
        "post",
        "/api/v1/editorial/publications",
        {
            "title": title,
            "summary": f"Acceptance {title}",
            "body": body(f"body-token-{title}"),
            "category": "regulations",
            "audience": audience,
        },
    )
    assert created.status_code == 201, created.data
    publication_id = created.data["id"]
    published = request(
        "editor-1",
        "post",
        f"/api/v1/editorial/publications/{publication_id}/publish",
    )
    assert published.status_code == 200, published.data
    return publication_id


suffix = uuid.uuid4().hex[:8]
org_id = create_and_publish(
    f"Регламент VPN {suffix}",
    {"everyone": False, "org_units": ["engineering"], "employees": [], "module_roles": []},
)
all_id = create_and_publish(
    f"Для всех {suffix}",
    {"everyone": True, "org_units": [], "employees": [], "module_roles": []},
)
employee_id = create_and_publish(
    f"Лично {suffix}",
    {"everyone": False, "org_units": [], "employees": ["employee-1"], "module_roles": []},
)
role_id = create_and_publish(
    f"Для редакторов {suffix}",
    {"everyone": False, "org_units": [], "employees": [], "module_roles": ["editor"]},
)

admin_feed = request("admin-1", "get", "/api/v1/news").data["results"]
employee_feed = request("employee-1", "get", "/api/v1/news").data["results"]
editor_feed = request("editor-1", "get", "/api/v1/news").data["results"]
assert org_id in {item["id"] for item in admin_feed}
assert org_id not in {item["id"] for item in employee_feed}
assert all_id in {item["id"] for item in admin_feed} & {item["id"] for item in employee_feed}
assert employee_id in {item["id"] for item in employee_feed}
assert employee_id not in {item["id"] for item in admin_feed}
assert role_id in {item["id"] for item in editor_feed}
assert role_id not in {item["id"] for item in employee_feed}

search = request("admin-1", "get", "/api/v1/news", {"q": f"VPN {suffix}"})
assert org_id in {item["id"] for item in search.data["results"]}
body_search = request("admin-1", "get", "/api/v1/news", {"q": "body-token-Регламент"})
assert org_id in {item["id"] for item in body_search.data["results"]}
summary_search = request("admin-1", "get", "/api/v1/news", {"q": f"Acceptance VPN {suffix}"})
assert org_id in {item["id"] for item in summary_search.data["results"]}
assert request("employee-1", "get", f"/api/v1/news/{org_id}").status_code == 404
assert request("employee-1", "get", "/api/v1/news", {"q": f"VPN {suffix}"}).data["results"] == []
assert org_id in {
    item["id"]
    for item in request("admin-1", "get", "/api/v1/news", {"unread": True}).data["results"]
}
assert request("admin-1", "get", f"/api/v1/news/{org_id}").status_code == 200
assert request("admin-1", "get", f"/api/v1/news/{org_id}").status_code == 200
assert PublicationView.objects.filter(publication_id=org_id, user__portal_id="admin-1").count() == 1
assert org_id not in {
    item["id"]
    for item in request("admin-1", "get", "/api/v1/news", {"unread": True}).data["results"]
}

filtered = request(
    "admin-1",
    "get",
    "/api/v1/news",
    {
        "category": "regulations",
        "author": "editor-1",
        "date_from": timezone.localdate().isoformat(),
        "date_to": timezone.localdate().isoformat(),
    },
)
assert org_id in {item["id"] for item in filtered.data["results"]}

category = Category.objects.get(slug="regulations")
author = User.objects.get(portal_id="editor-1")
for index in range(22):
    publication = Publication.objects.create(
        title=f"Cursor {suffix} {index}",
        slug=f"cursor-{suffix}-{index}",
        summary="Cursor acceptance",
        body=body(f"Cursor {index}"),
        category=category,
        author=author,
        status=Publication.Status.PUBLISHED,
        published_at=timezone.now() - timedelta(seconds=index),
    )
    replace_audience_rules(publication, everyone=True)

default_page = request("employee-1", "get", "/api/v1/news")
assert len(default_page.data["results"]) == 20
first_page = request("employee-1", "get", "/api/v1/news", {"page_size": 5})
cursor = parse_qs(urlparse(first_page.data["next"]).query)["cursor"][0]
second_page = request("employee-1", "get", "/api/v1/news", {"page_size": 5, "cursor": cursor})
assert not {item["id"] for item in first_page.data["results"]}.intersection(
    item["id"] for item in second_page.data["results"]
)
assert request("blocked-1", "get", "/api/v1/news").status_code == 403

print(
    {
        "result": "PASS",
        "org_publication": org_id,
        "all_publication": all_id,
        "employee_publication": employee_id,
        "role_publication": role_id,
        "unique_views": 1,
        "default_page_size": 20,
        "cursor_overlap": 0,
    }
)
