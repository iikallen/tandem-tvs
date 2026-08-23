from typing import Protocol

from django.http import HttpRequest

from .types import PortalEmployee, PortalHealth, PortalIdentity, PortalOrgUnit


class PortalAdapter(Protocol):
    def authenticate_request(self, request: HttpRequest) -> PortalIdentity | None: ...

    def get_employee(self, portal_id: str) -> PortalEmployee | None: ...

    def search_employees(self, query: str) -> tuple[PortalEmployee, ...]: ...

    def list_org_units(self) -> tuple[PortalOrgUnit, ...]: ...

    def healthcheck(self) -> PortalHealth: ...
