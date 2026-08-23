import hashlib
import json
import secrets
from dataclasses import dataclass

import redis
from django.conf import settings


@dataclass(frozen=True)
class TicketClaims:
    user_id: int
    publication_id: str


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.REALTIME_REDIS_URL, decode_responses=True)


def _key(token: str) -> str:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return f"realtime-ticket:{digest}"


def create_ticket(*, user_id: int, publication_id: object) -> tuple[str, int]:
    ttl = int(settings.REALTIME_TICKET_TTL_SECONDS)
    payload = json.dumps(
        {"user_id": user_id, "publication_id": str(publication_id)}, separators=(",", ":")
    )
    client = _client()
    for _ in range(3):
        token = secrets.token_urlsafe(32)
        if client.set(_key(token), payload, ex=ttl, nx=True):
            return token, ttl
    raise RuntimeError("Could not allocate a realtime ticket.")


def consume_ticket(token: str) -> TicketClaims | None:
    if not token or len(token) > 256:
        return None
    payload = _client().getdel(_key(token))
    if not isinstance(payload, (str, bytes, bytearray)):
        return None
    try:
        claims = json.loads(payload)
        return TicketClaims(
            user_id=int(claims["user_id"]), publication_id=str(claims["publication_id"])
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
