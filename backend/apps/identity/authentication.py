from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from .portal import get_portal_adapter
from .services import deactivate_projection, provision_user


class PortalAuthentication(BaseAuthentication):
    def authenticate(self, request):
        adapter = get_portal_adapter()
        identity = adapter.authenticate_request(request)
        if identity is None:
            return None

        employee = adapter.get_employee(identity.portal_id)
        if employee is None:
            raise AuthenticationFailed(
                "Portal identity is not mapped to an employee.",
                code="unknown_portal_identity",
            )

        if not employee.is_active:
            deactivate_projection(employee.portal_id)
            raise PermissionDenied(
                "Portal account is blocked.",
                code="portal_account_blocked",
            )

        user = provision_user(adapter, employee)
        return user, identity

    def authenticate_header(self, request) -> str:
        return "Portal"
