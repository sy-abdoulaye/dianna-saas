import pytest

from apps.core.status import KINDS, STATUSES, get_status


def test_every_status_uses_a_known_color_role():
    for domain, values in STATUSES.items():
        for value, status in values.items():
            assert status.kind in KINDS, f"{domain}.{value}"
            assert str(status.label)


def test_labels_follow_the_prototype():
    assert get_status("request", "pending").label == "En attente"
    assert get_status("request", "approved").label == "Validée"
    assert get_status("report", "approved").label == "Validé"
    assert get_status("employee", "upcoming").label == "Arrivée prochaine"


def test_unknown_status_is_a_programming_error():
    with pytest.raises(KeyError, match=r"request\.unknown"):
        get_status("request", "unknown")
