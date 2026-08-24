from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.identity.managers import UserManager
from apps.identity.models import User
from apps.organization.models import OrgUnit


def create_user(**fields) -> User:
    manager = User.objects
    assert isinstance(manager, UserManager)
    return manager.create_user(**fields)


@pytest.mark.django_db
def test_portal_id_is_unique_and_immutable():
    user = create_user(portal_id="employee-1", full_name="Алия Байжанова")

    with pytest.raises(IntegrityError), transaction.atomic():
        create_user(portal_id="employee-1", full_name="Другой сотрудник")

    user.portal_id = "replacement-id"
    with pytest.raises(ValidationError):
        user.save()


@pytest.mark.django_db
def test_portal_linked_user_can_have_a_local_password():
    user = create_user(portal_id="employee-1", full_name="Алия Байжанова")
    assert not user.has_usable_password()

    user.set_password("must-not-survive")
    user.save()
    assert user.check_password("must-not-survive")


@pytest.mark.django_db
def test_projected_user_can_be_inactive():
    user = create_user(
        portal_id="blocked-1",
        full_name="Заблокированный сотрудник",
        is_active=False,
    )
    assert user.is_active is False


@pytest.mark.django_db
def test_organization_hierarchy_and_parent_relation():
    company = OrgUnit.objects.create(external_id="company", name="Tandem", kind="company")
    department = OrgUnit.objects.create(
        external_id="department-communications",
        name="Коммуникации",
        kind="department",
        parent=company,
    )
    user = create_user(
        portal_id="employee-1",
        full_name="Алия Байжанова",
        org_unit=department,
    )

    assert department.parent == company
    assert list(OrgUnit.objects.filter(parent=company)) == [department]
    assert user.org_unit == department
    assert list(User.objects.filter(org_unit=department)) == [user]


@pytest.mark.django_db
def test_projection_timestamps_are_populated_and_updated():
    before = timezone.now() - timedelta(seconds=1)
    unit = OrgUnit.objects.create(external_id="company", name="Tandem")
    user = create_user(portal_id="employee-1", full_name="Алия Байжанова")

    assert unit.created_at >= before
    assert unit.updated_at >= unit.created_at
    assert user.created_at >= before
    assert user.updated_at >= user.created_at

    original_updated_at = user.updated_at
    user.job_title = "Редактор"
    user.save()
    assert user.updated_at >= original_updated_at
