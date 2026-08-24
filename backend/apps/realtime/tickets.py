import hashlib
import json
import secrets
import time

import redis
from django.conf import settings

from .claims import RealtimeScope, RealtimeTicket


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.REALTIME_REDIS_URL, decode_responses=True)


def _key(token: str) -> str:
    return f"realtime-ticket:{hashlib.sha256(token.encode()).hexdigest()}"


def create_ticket(
    *,
    user_id: int,
    security_epoch: int,
    session_key: str,
    scope: RealtimeScope,
    resource_id: object | None = None,
) -> tuple[str, int]:
    ttl = int(settings.REALTIME_TICKET_TTL_SECONDS)
    client = _client()
    for _ in range(3):
        token = secrets.token_urlsafe(32)
        from .session_security import session_fingerprint

        fingerprint = session_fingerprint(session_key)
        payload = json.dumps(
            {
                "user_id": user_id,
                "security_epoch": security_epoch,
                "session_key": session_key,
                "session_fingerprint": fingerprint,
                "scope": scope,
                "resource_id": str(resource_id) if resource_id is not None else None,
                "expires_at": int(time.time()) + ttl,
                "nonce": secrets.token_urlsafe(16),
            },
            separators=(",", ":"),
        )
        if client.set(_key(token), payload, ex=ttl, nx=True):
            return token, ttl
    raise RuntimeError("Could not allocate a realtime ticket.")


def consume_ticket(token: str) -> RealtimeTicket | None:
    if not token or len(token) > 256:
        return None
    payload = _client().getdel(_key(token))
    if not isinstance(payload, str | bytes | bytearray):
        return None
    try:
        claims = json.loads(payload)
        expires_at = int(claims["expires_at"])
        nonce = str(claims["nonce"])
        if expires_at < int(time.time()) or not nonce:
            return None
        return RealtimeTicket(
            user_id=int(claims["user_id"]),
            security_epoch=int(claims["security_epoch"]),
            session_key=str(claims["session_key"]),
            session_fingerprint=str(claims["session_fingerprint"]),
            scope=RealtimeScope(claims["scope"]),
            resource_id=str(claims["resource_id"])
            if claims.get("resource_id") is not None
            else None,
            expires_at=expires_at,
            nonce=nonce,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
