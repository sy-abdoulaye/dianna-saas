from apps.core.navigation import NAV, build_demo_nav, build_nav


def test_menu_groups_follow_the_prototype():
    labels = [str(group.label) for group in NAV]
    assert labels == ["", "Demandes", "Activité", "Talents", "Entreprise"]


def test_real_menu_hides_entries_whose_route_does_not_exist_yet():
    items = [item for group in build_nav() for item in group.items]
    # Aucun module n'est livré au lot 0 : seules les entrées « Bientôt » restent, sans lien.
    assert items
    assert all(item.soon and item.url is None for item in items)


def test_demo_menu_marks_active_entry_and_counts():
    groups = build_demo_nav(current="telework", counts={"telework": 2})
    items = {item.key: item for group in groups for item in group.items}
    assert items["telework"].active
    assert items["telework"].count == 2
    assert not items["people"].active
    assert items["recruitment"].roles == ("manager", "hr", "admin")
