from django.http import HttpRequest

from .exceptions import PortalUnavailableError
from .types import PortalEmployee, PortalHealth, PortalIdentity, PortalOrgUnit


class UnavailablePortalAdapter:
    """Fail-closed production placeholder until the portal contract is supplied."""

    def authenticate_request(self, request: HttpRequest) -> PortalIdentity | None:
        raise PortalUnavailableError

    def get_employee(self, portal_id: str) -> PortalEmployee | None:
        raise PortalUnavailableError

    def search_employees(self, query: str, *, limit: int) -> tuple[PortalEmployee, ...]:
        raise PortalUnavailableError

    def list_org_units(self) -> tuple[PortalOrgUnit, ...]:
        raise PortalUnavailableError

    def healthcheck(self) -> PortalHealth:
        return PortalHealth(available=False, detail="Portal integration is not configured")
