from typing import Protocol

from django.http import HttpRequest

from .types import (
    PortalEmployee,
    PortalHealth,
    PortalIdentity,
    PortalOrgUnit,
    PortalPositionGroup,
)


class PortalAdapter(Protocol):
    def authenticate_request(self, request: HttpRequest) -> PortalIdentity | None: ...

    def get_employee(self, portal_id: str) -> PortalEmployee | None: ...

    def search_employees(
        self,
        query: str,
        *,
        limit: int,
    ) -> tuple[PortalEmployee, ...]: ...

    def list_org_units(self) -> tuple[PortalOrgUnit, ...]: ...

    def list_position_groups(self) -> tuple[PortalPositionGroup, ...]: ...

    def healthcheck(self) -> PortalHealth: ...
