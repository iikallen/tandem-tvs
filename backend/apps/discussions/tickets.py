from apps.identity.models import User
from apps.realtime.claims import RealtimeScope, RealtimeTicket
from apps.realtime.tickets import consume_ticket as consume_ticket
from apps.realtime.tickets import create_ticket as create_realtime_ticket

TicketClaims = RealtimeTicket


def create_ticket(*, user_id: int, publication_id: object) -> tuple[str, int]:
    security_epoch = User.objects.only("security_epoch").get(pk=user_id).security_epoch
    return create_realtime_ticket(
        user_id=user_id,
        security_epoch=security_epoch,
        scope=RealtimeScope.NEWS_PUBLICATION,
        resource_id=publication_id,
    )
