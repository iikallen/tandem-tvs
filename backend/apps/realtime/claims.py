from dataclasses import dataclass
from enum import StrEnum


class RealtimeScope(StrEnum):
    NEWS_PUBLICATION = "NEWS_PUBLICATION"
    MESSENGER = "MESSENGER"


@dataclass(frozen=True)
class RealtimeTicket:
    user_id: int
    security_epoch: int
    scope: RealtimeScope
    resource_id: str | None = None
