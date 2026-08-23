from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PortalIdentity:
    portal_id: str


@dataclass(frozen=True, slots=True)
class PortalEmployee:
    portal_id: str
    full_name: str
    is_active: bool
    email: str = ""
    job_title: str = ""
    phone: str = ""
    avatar_url: str = ""
    org_unit_external_id: str | None = None
    position_group_external_id: str = ""
    position_group_name: str = ""
    roles: tuple[str, ...] = ("employee",)


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
