"""Matrice docs/04-permissions.md (fonctions pures)."""

import pytest

from apps.core import permissions
from apps.core.permissions import RULES, can, scope, scope_queryset
from apps.core.tenancy import tenant_context
from apps.people.models import Employee, Role
from tests.factories import EmployeeFactory


def test_every_rule_has_four_columns():
    for action, rule in RULES.items():
        assert len(rule) == 4, action


def test_unknown_action_is_a_programming_error(company_a):
    with pytest.raises(KeyError):
        can(company_a.employee, "people.fly")


def test_anonymous_has_no_rights():
    assert not can(None, "people.view_list")


@pytest.mark.parametrize(
    ("who", "action", "expected"),
    [
        ("employee", "people.view_list", True),
        ("employee", "people.view_left", False),
        ("hr", "people.view_left", True),
        ("employee", "people.manage", False),
        ("hr", "people.manage", True),
        ("hr", "people.assign_role", False),
        ("admin", "people.assign_role", True),
        ("hr", "admin.manage", False),
        ("admin", "admin.manage", True),
        ("employee", "surveys.view_results", False),
        ("manager", "surveys.view_results", True),
        ("employee", "announcements.manage", False),
        ("hr", "announcements.manage", True),
        ("employee", "requests.decide", False),
        ("manager", "requests.decide", True),
    ],
)
def test_global_rights_by_profile(company_a, who, action, expected):
    assert can(getattr(company_a, who), action) is expected


def test_team_rights_come_from_direct_reports_not_from_the_profile(company_a):
    # Louise a le profil Manager ET une collaboratrice directe (Camille).
    assert scope(company_a.manager, "requests.decide") == permissions.TEAM
    # Un profil Manager sans équipe n'a que les droits d'un salarié (L1-02).
    lonely = EmployeeFactory(company=company_a.company, role=Role.MANAGER, user=None)
    assert scope(lonely, "requests.decide") is None
    # Un salarié qui a des collaborateurs directs a les droits « Équipe ».
    EmployeeFactory(company=company_a.company, manager=company_a.employee, user=None)
    employee = Employee.all_companies.get(pk=company_a.employee.pk)
    assert scope(employee, "requests.decide") == permissions.TEAM


def test_team_scope_on_objects(company_a):
    manager, employee = company_a.manager, company_a.employee
    stranger = company_a.pending  # sans manager
    assert can(manager, "people.view_hr", manager)
    assert not can(manager, "people.view_hr", employee)  # V-07
    assert can(manager, "careers.view", employee)
    assert not can(manager, "careers.view", stranger)
    assert can(company_a.hr, "careers.view", stranger)


def test_nobody_decides_for_themselves(company_a):
    hr = company_a.hr
    assert can(hr, "requests.decide", company_a.employee)
    assert not can(hr, "requests.decide", hr)
    assert not can(company_a.manager, "careers.evaluate", company_a.manager)


def test_objects_of_another_company_are_never_allowed(company_a, company_b):
    assert not can(company_a.admin, "people.view_hr", company_b.employee)


def test_service_scope_includes_team_members_of_other_services(company_a):
    other = EmployeeFactory(company=company_a.company, manager=company_a.manager, user=None)
    assert other.service_id != company_a.manager.service_id
    manager = Employee.all_companies.get(pk=company_a.manager.pk)
    assert can(manager, "planning.view", other)  # L1-06
    assert not can(company_a.employee, "planning.view", other)
    assert can(company_a.employee, "planning.view", company_a.manager)  # même service


def test_owner_of_uses_the_declared_field(company_a):
    from django.core.exceptions import ImproperlyConfigured

    class Request:
        permission_owner_field = "requester"
        requester = company_a.employee
        company_id = company_a.company.pk

    assert permissions.owner_of(Request()) == company_a.employee
    assert permissions.owner_of(company_a.employee) == company_a.employee
    with pytest.raises(ImproperlyConfigured):
        permissions.owner_of(object())


def test_scope_queryset(company_a):
    with tenant_context(company_a.company):
        everyone = Employee.objects.all()
        mine = scope_queryset(company_a.employee, everyone, "people.view_hr")
        assert list(mine) == [company_a.employee]
        team = scope_queryset(company_a.manager, everyone, "requests.view")
        assert set(team) == {company_a.manager, company_a.employee}
        assert (
            scope_queryset(company_a.hr, everyone, "people.view_left").count() == everyone.count()
        )
        assert scope_queryset(company_a.employee, everyone, "people.manage").count() == 0
        decide = scope_queryset(company_a.hr, everyone, "requests.decide")
        assert company_a.hr not in decide
        service = scope_queryset(company_a.employee, everyone, "planning.view")
        assert company_a.manager in service


def test_scope_queryset_with_owner_field(company_a):
    from apps.core.models import Notification

    with tenant_context(company_a.company):
        rows = scope_queryset(company_a.manager, Notification.objects.all(), "requests.view")
        assert list(rows) == [company_a.notification]  # notification de Camille, son équipe
