from apps.identity.models import AccessGrant, User
from apps.identity.permissions import has_module_access

from .claims import RealtimeScope, RealtimeTicket
from .session_security import ticket_session_deadline


def valid_user_for_ticket(claims: RealtimeTicket) -> User | None:
    user = User.objects.filter(pk=claims.user_id, is_active=True).first()
    if (
        user is None
        or user.security_epoch != claims.security_epoch
        or ticket_session_deadline(claims) is None
    ):
        return None
    if claims.scope == RealtimeScope.MESSENGER and not has_module_access(
        user, AccessGrant.Module.MESSENGER
    ):
        return None
    return user


def valid_user_and_session_for_ticket(
    claims: RealtimeTicket,
) -> tuple[User, int] | None:
    user = valid_user_for_ticket(claims)
    deadline = ticket_session_deadline(claims)
    return (user, deadline) if user is not None and deadline is not None else None
