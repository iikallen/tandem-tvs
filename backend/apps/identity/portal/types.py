from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PortalIdentity:
    portal_id: str


@dataclass(frozen=True, slots=True)
class PortalEmployee:
    portal_id: str
    full_name: str
    email: str = ""
    job_title: str = ""
    phone: str = ""
    avatar_url: str = ""
    org_unit_external_id: str | None = None
    roles: tuple[str, ...] = ("employee",)
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class PortalOrgUnit:
    external_id: str
    name: str
    kind: str = ""
    parent_external_id: str | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class PortalHealth:
    available: bool
    detail: str = ""
