"""Run Stage 3 acceptance against configured PostgreSQL and Redis."""

import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import close_old_connections, connection  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.discussions.models import Comment, Reaction  # noqa: E402
from apps.discussions.services import put_reaction  # noqa: E402
from apps.discussions.tickets import consume_ticket, create_ticket  # noqa: E402
from apps.identity.models import User  # noqa: E402
from apps.publications.models import Publication  # noqa: E402

assert connection.vendor == "postgresql", "Stage 3 acceptance requires PostgreSQL"
assert settings.REALTIME_REDIS_URL.rstrip("/").endswith("/1")

client = APIClient()


def request(portal_id: str, method: str, path: str, data=None):
    client.force_authenticate(user=None)
    user = User.objects.get(portal_id=portal_id)
    if user.is_active:
        client.force_authenticate(user=user)
    return getattr(client, method)(path, data, format="json", HTTP_HOST="localhost")


publication_id = str(uuid.UUID("00000000-0000-0000-0000-000000003001"))
from django.core.management import call_command  # noqa: E402

call_command("seed_stage3_demo", verbosity=0)
comments_path = f"/api/v1/news/{publication_id}/comments"
created = request("employee-1", "post", comments_path, {"body": "PostgreSQL\r\npersistence"})
assert created.status_code == 201, created.data
comment_id = created.data["id"]
assert (
    request("author-1", "get", comments_path).data["results"][0]["body"]
    == "PostgreSQL\npersistence"
)
assert request("admin-1", "get", comments_path).status_code == 404

like_path = f"/api/v1/news/{publication_id}/reactions/LIKE"
assert request("employee-1", "put", like_path).status_code == 201
assert request("employee-1", "put", like_path).status_code == 200

reaction_user = User.objects.get(portal_id="employee-1")
publication = Publication.objects.get(pk=publication_id)
Reaction.objects.filter(
    publication=publication,
    user=reaction_user,
    reaction_type=Reaction.Type.LIKE,
).delete()


def concurrent_like(_attempt: int) -> str:
    close_old_connections()
    try:
        thread_user = User.objects.get(pk=reaction_user.pk)
        thread_publication = Publication.objects.get(pk=publication.pk)
        reaction, _created = put_reaction(
            publication=thread_publication,
            user=thread_user,
            reaction_type=Reaction.Type.LIKE,
        )
        return str(reaction.pk)
    finally:
        close_old_connections()


with ThreadPoolExecutor(max_workers=8) as executor:
    reaction_ids = list(executor.map(concurrent_like, range(8)))
assert len(set(reaction_ids)) == 1
assert (
    Reaction.objects.filter(
        publication=publication,
        user=reaction_user,
        reaction_type=Reaction.Type.LIKE,
    ).count()
    == 1
)

summary = request("author-1", "get", f"/api/v1/news/{publication_id}/reactions")
assert summary.data["counts"] == {"LIKE": 1}
detail = request("author-1", "get", f"/api/v1/news/{publication_id}")
assert detail.data["comment_count"] == 1
assert detail.data["reaction_count"] == 1

user_id = Comment.objects.get(pk=comment_id).author.pk
ticket, _ = create_ticket(user_id=user_id, publication_id=publication_id)
assert consume_ticket(ticket) is not None
assert consume_ticket(ticket) is None

original_ttl = settings.REALTIME_TICKET_TTL_SECONDS
settings.REALTIME_TICKET_TTL_SECONDS = 1
try:
    expired_ticket, _ = create_ticket(user_id=user_id, publication_id=publication_id)
    time.sleep(1.1)
    assert consume_ticket(expired_ticket) is None
finally:
    settings.REALTIME_TICKET_TTL_SECONDS = original_ttl

connection.close()
assert Comment.objects.get(pk=comment_id).body == "PostgreSQL\npersistence"
assert Reaction.objects.filter(publication_id=publication_id, reaction_type="LIKE").count() == 1
assert (
    Publication.objects.visible_to(Comment.objects.get(pk=comment_id).author)
    .filter(pk=publication_id)
    .exists()
)

print(
    {
        "result": "PASS",
        "database": connection.vendor,
        "redis_transport_db": 1,
        "publication": publication_id,
        "comment": comment_id,
        "ticket_reuse": "denied",
        "ticket_expiry": "denied",
        "reaction_concurrency": "one-row",
        "outsider": 404,
    }
)
