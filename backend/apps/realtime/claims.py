from dataclasses import dataclass
from enum import StrEnum


class RealtimeScope(StrEnum):
    NEWS_PUBLICATION = "NEWS_PUBLICATION"
    MESSENGER = "MESSENGER"
    NOTIFICATIONS = "NOTIFICATIONS"


@dataclass(frozen=True)
class RealtimeTicket:
    user_id: int
    security_epoch: int
    session_key: str
    session_fingerprint: str
    scope: RealtimeScope
    resource_id: str | None = None
    expires_at: int = 0
    nonce: str = ""
