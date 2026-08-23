from django.conf import settings
from django.http import HttpRequest

from .types import PortalEmployee, PortalHealth, PortalIdentity, PortalOrgUnit

ORG_UNITS = (
    PortalOrgUnit(external_id="company", name="Tandem TVS", kind="company"),
    PortalOrgUnit(
        external_id="communications",
        name="Корпоративные коммуникации",
        kind="department",
        parent_external_id="company",
    ),
    PortalOrgUnit(
        external_id="engineering",
        name="Разработка",
        kind="department",
        parent_external_id="company",
    ),
)

EMPLOYEES = (
    PortalEmployee(
        portal_id="employee-1",
        full_name="Алия Байжанова",
        is_active=True,
        email="a.baizhanova@tandem.example",
        job_title="Специалист",
        position_group_external_id="specialists",
        position_group_name="Специалисты",
        phone="+7 700 000 00 01",
        org_unit_external_id="communications",
    ),
    PortalEmployee(
        portal_id="author-1",
        full_name="Серик Жаксибеков",
        is_active=True,
        email="s.zhaksibekov@tandem.example",
        job_title="Автор",
        position_group_external_id="communications-authors",
        position_group_name="Авторы коммуникаций",
        org_unit_external_id="communications",
        roles=("employee", "author"),
    ),
    PortalEmployee(
        portal_id="editor-1",
        full_name="Дмитрий Орлов",
        is_active=True,
        email="d.orlov@tandem.example",
        job_title="Редактор",
        position_group_external_id="communications-editors",
        position_group_name="Редакторы коммуникаций",
        org_unit_external_id="communications",
        roles=("employee", "editor"),
    ),
    PortalEmployee(
        portal_id="admin-1",
        full_name="Нурлан Касымов",
        is_active=True,
        email="n.kassymov@tandem.example",
        job_title="Администратор",
        position_group_external_id="administrators",
        position_group_name="Администраторы",
        org_unit_external_id="engineering",
        roles=("employee", "admin"),
    ),
    PortalEmployee(
        portal_id="blocked-1",
        full_name="Заблокированный сотрудник",
        is_active=False,
        email="blocked@tandem.example",
        org_unit_external_id="engineering",
    ),
)


class MockPortalAdapter:
    def authenticate_request(self, request: HttpRequest) -> PortalIdentity | None:
        portal_id = getattr(request, "_mock_portal_id", None)
        if portal_id is None:
            portal_id = request.headers.get("X-Mock-Portal-User", settings.MOCK_PORTAL_USER_ID)
        return PortalIdentity(portal_id=portal_id) if portal_id else None

    def get_employee(self, portal_id: str) -> PortalEmployee | None:
        return next((employee for employee in EMPLOYEES if employee.portal_id == portal_id), None)

    def search_employees(self, query: str, *, limit: int) -> tuple[PortalEmployee, ...]:
        normalized_query = query.casefold().strip()
        if not normalized_query:
            return ()

        return tuple(
            employee
            for employee in EMPLOYEES
            if normalized_query
            in " ".join(
                (
                    employee.full_name,
                    employee.email,
                    employee.job_title,
                    employee.portal_id,
                )
            ).casefold()
        )[:limit]

    def list_org_units(self) -> tuple[PortalOrgUnit, ...]:
        return ORG_UNITS

    def healthcheck(self) -> PortalHealth:
        return PortalHealth(available=True)
