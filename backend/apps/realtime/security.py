from apps.identity.models import AccessGrant, User
from apps.identity.permissions import has_module_access

from .claims import RealtimeScope, RealtimeTicket


def valid_user_for_ticket(claims: RealtimeTicket) -> User | None:
    user = User.objects.filter(pk=claims.user_id, is_active=True).first()
    if user is None or user.security_epoch != claims.security_epoch:
        return None
    if claims.scope == RealtimeScope.MESSENGER and not has_module_access(
        user, AccessGrant.Module.MESSENGER
    ):
        return None
    return user
