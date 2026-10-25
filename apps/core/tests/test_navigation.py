from types import SimpleNamespace

from apps.core.models import Module
from apps.core.navigation import NAV, build_demo_nav, build_nav


def person(role="employee", has_reports=False):
    return SimpleNamespace(role=role, has_reports=has_reports)


def keys(groups):
    return [item.key for group in groups for item in group.items]


def test_menu_groups_follow_the_prototype():
    labels = [str(group.label) for group in NAV]
    assert labels == ["", "Demandes", "Activité", "Talents", "Entreprise"]


def test_real_menu_shows_existing_routes_and_soon_entries_without_link():
    groups = build_nav(person(), set(Module.values))
    items = {item.key: item for group in groups for item in group.items}
    assert items["dashboard"].url == "/"
    assert items["workload"].soon and items["workload"].url is None
    assert items["telework"].url == "/teletravail/"
    # Lot 5 : transport et matériel ont leurs écrans.
    assert items["transport"].url == "/transport/"
    assert items["equipment"].url == "/materiel/"
    # Lot 6 : communication interne et questionnaires.
    assert items["announcements"].url == "/annonces/"
    assert items["surveys"].url == "/questionnaires/"
    # Lot 7 : carrière et évaluations.
    assert items["careers"].url == "/carriere/"


def test_recruitment_is_shown_to_people_with_reports_not_to_the_manager_profile_alone():
    assert "recruitment" not in keys(build_nav(person(), set()))
    assert "recruitment" not in keys(build_nav(person("manager"), set()))
    assert "recruitment" in keys(build_nav(person("employee", has_reports=True), set()))
    assert "recruitment" in keys(build_nav(person("hr"), set()))


def test_demo_menu_marks_active_entry_and_counts():
    groups = build_demo_nav(current="telework", counts={"telework": 2})
    items = {item.key: item for group in groups for item in group.items}
    assert items["telework"].active
    assert items["telework"].count == 2
    assert not items["people"].active
    assert items["recruitment"].roles == ("manager", "hr", "admin")
