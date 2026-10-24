"""Briques communes à registre : table unique des contraintes de base (L5-19) et vue
d'annulation générique (L0-03)."""

import pytest

from apps.core import constraints, undo


def test_every_application_writes_its_constraints_in_the_single_table():
    names = set(constraints.CONSTRAINT_MESSAGES)
    assert {
        "telework_one_active_per_day",
        "transport_amount_range",
        "people_employee_email_ci_unique",
        "equipment_serial_unique",
    } <= names
    with pytest.raises(ValueError, match="déjà inscrites"):
        constraints.register({"equipment_serial_unique": (None, "doublon")})


def test_an_unknown_constraint_gets_the_default_message():
    class DatabaseCauseError(Exception):
        class diag:  # noqa: N801 (imite l'objet diag de psycopg)
            constraint_name = "inconnue"

    error = Exception()
    error.__cause__ = DatabaseCauseError()
    assert constraints.translate(error, "Message par défaut") == (None, "Message par défaut")


def test_each_undoable_action_has_a_single_handler():
    assert {
        "requests.submit",
        "requests.cancel_approved",
        "equipment.assign",
        "equipment.repair",
        "people.archive",
        "announcements.delete",
    } <= set(undo.HANDLERS)
    with pytest.raises(ValueError, match="déjà inscrite"):
        undo.register("people.archive", lambda request, payload: None, refresh="x")


@pytest.mark.django_db
def test_a_token_is_refused_on_the_url_of_another_application(client_for, company_a):
    """Un jeton d'annulation de matériel présenté à l'URL des annonces : page absente."""
    import json

    client = client_for(company_a.hr)
    stock = company_a.requests["stock_item"]
    response = client.post(
        f"/materiel/parc/{stock.public_id}/attribuer/", {"employee": company_a.manager.pk}
    )
    undo_url = json.loads(response["HX-Trigger"])["toast"]["undo_url"]
    token = undo_url.rstrip("/").rsplit("/", 1)[1]
    assert client.post(f"/annonces/annuler/{token}/").status_code == 404
    assert client.post(undo_url).status_code == 204
