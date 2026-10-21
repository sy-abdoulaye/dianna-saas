"""Suivi du matériel : critères d'acceptation de docs/modules/07-materiel.md (L5-08 à L5-11)."""

import json
import threading

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.core.models import AuditLog, Company, Notification
from apps.core.tenancy import tenant_context
from apps.equipment import services
from apps.equipment.models import (
    EquipmentAssignment,
    EquipmentEvent,
    EquipmentIssue,
    EquipmentItem,
    EquipmentRequest,
)
from apps.people.models import Employee
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db


def toast(response):
    return json.loads(response["HX-Trigger"])["toast"]


def reload(item):
    return EquipmentItem.all_companies.get(pk=item.pk)


@pytest.mark.parametrize(
    "path",
    [
        "/materiel/parc/ajouter/",
        "/materiel/parc/{stock}/attribuer/",
        "/materiel/parc/{held}/restituer/",
        "/materiel/parc/{held}/",
        "/materiel/parc/{stock}/retirer/",
    ],
)
def test_employee_has_no_park_and_gets_403(client_for, company_a, path):
    url = path.format(
        stock=company_a.requests["stock_item"].public_id, held=company_a.requests["item"].public_id
    )
    client = client_for(company_a.employee)
    assert client.get(url).status_code == 403
    page = client.get("/materiel/?onglet=parc").content.decode()
    assert 'href="/materiel/?onglet=parc"' not in page and "Mon matériel" in page


def test_hr_adds_an_item_and_serial_numbers_are_unique(client_for, company_a):
    client = client_for(company_a.hr)
    ok = client.post(
        "/materiel/parc/ajouter/",
        {"kind": "phone", "model": "iPhone 15", "serial_number": " dn 77 "},
    )
    assert ok.status_code == 204
    assert EquipmentItem.all_companies.filter(serial_number="DN77").exists()
    twice = client.post(
        "/materiel/parc/ajouter/", {"kind": "phone", "model": "iPhone 15", "serial_number": "Dn77"}
    )
    assert twice.status_code == 422
    assert "Ce numéro de série existe déjà dans le parc." in twice.content.decode()


def test_assign_then_undo_puts_the_item_back_in_stock(client_for, company_a):
    stock = company_a.requests["stock_item"]
    client = client_for(company_a.hr)
    response = client.post(
        f"/materiel/parc/{stock.public_id}/attribuer/", {"employee": company_a.manager.pk}
    )
    assert response.status_code == 204
    item = reload(stock)
    assert item.status == "assigned" and item.holder_id == company_a.manager.pk
    assert Notification.all_companies.filter(
        recipient=company_a.manager, text__startswith="Un équipement vous a été attribué"
    ).exists()
    undo = client.post(toast(response)["undo_url"])
    assert toast(undo)["title"] == "Attribution annulée"
    item = reload(stock)
    assert item.status == "in_stock" and item.holder is None
    assert not EquipmentAssignment.all_companies.filter(item=item).exists()
    assert not Notification.all_companies.filter(
        recipient=company_a.manager, text__startswith="Un équipement vous a été attribué"
    ).exists()


def test_an_assigned_item_cannot_be_assigned_again(client_for, company_a):
    held = company_a.requests["item"]
    response = client_for(company_a.hr).post(
        f"/materiel/parc/{held.public_id}/attribuer/", {"employee": company_a.manager.pk}
    )
    assert response.status_code == 409
    assert toast(response)["title"] == "Cet équipement est déjà attribué."
    assert reload(held).holder_id == company_a.employee.pk


def test_the_database_allows_one_open_assignment_and_a_coherent_holder(company_a):
    held = company_a.requests["item"]
    with tenant_context(company_a.company):
        with pytest.raises(IntegrityError), transaction.atomic():
            EquipmentAssignment.objects.create(
                item=held, employee=company_a.manager, assigned_at=timezone.now()
            )
        with pytest.raises(IntegrityError), transaction.atomic():
            EquipmentItem.objects.filter(pk=held.pk).update(status="in_stock")
        with pytest.raises(IntegrityError), transaction.atomic():
            EquipmentItem.objects.create(
                kind="other", model="x", serial_number="Z1", status="assigned"
            )


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_assignments_give_one_holder(company_a):
    company = Company.objects.get(pk=company_a.company.pk)
    hr = Employee.all_companies.get(pk=company_a.hr.pk)
    people = [Employee.all_companies.get(pk=p.pk) for p in (company_a.manager, company_a.admin)]
    item = EquipmentItem.all_companies.get(pk=company_a.requests["stock_item"].pk)
    barrier = threading.Barrier(2)
    outcomes = []

    def assign(person):
        try:
            with tenant_context(company):
                barrier.wait()
                services.assign(item, person, actor=hr)
                outcomes.append("ok")
        except services.EquipmentError as error:
            outcomes.append(str(error.message))
        finally:
            connection.close()

    threads = [threading.Thread(target=assign, args=[p]) for p in people]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["Cet équipement est déjà attribué.", "ok"]
    assert (
        EquipmentAssignment.all_companies.filter(item=item, returned_at__isnull=True).count() == 1
    )


def test_return_repair_back_and_retire(client_for, company_a):
    held, stock = company_a.requests["item"], company_a.requests["stock_item"]
    client = client_for(company_a.hr)
    assert client.post(f"/materiel/parc/{held.public_id}/restituer/").status_code == 204
    item = reload(held)
    assert item.status == "in_stock" and item.holder is None
    assert EquipmentAssignment.all_companies.get(item=item).returned_at is not None
    assert client.post(f"/materiel/parc/{stock.public_id}/reparation/").status_code == 204
    assert reload(stock).status == "repair"
    assert client.post(f"/materiel/parc/{stock.public_id}/fin-reparation/").status_code == 204
    assert reload(stock).status == "in_stock"
    assert client.post(f"/materiel/parc/{stock.public_id}/retirer/").status_code == 204
    assert reload(stock).status == "retired"
    park = client.get("/materiel/?onglet=parc").content.decode()
    assert stock.serial_number not in park  # retirés masqués par défaut
    assert stock.serial_number in client.get("/materiel/?onglet=parc&etat=retired").content.decode()
    history = client.get(f"/materiel/parc/{stock.public_id}/").content.decode()
    for label in ("Envoyé en réparation", "Retour de réparation", "Retiré du parc"):
        assert label in history


def test_an_item_with_a_holder_cannot_be_retired(client_for, company_a):
    held = company_a.requests["item"]
    response = client_for(company_a.hr).post(f"/materiel/parc/{held.public_id}/retirer/")
    assert response.status_code == 409


def test_issue_is_reported_by_the_holder_and_handled_by_hr(client_for, company_a):
    held = company_a.requests["item"]
    holder = client_for(company_a.employee)
    url = f"/materiel/equipements/{held.public_id}/signaler/"
    assert client_for(company_a.manager).get(url).status_code == 404  # pas son équipement
    empty = holder.post(url, {"description": ""})
    assert "Décrivez le problème." in empty.content.decode()
    assert holder.post(url, {"description": "Le clavier ne répond plus"}).status_code == 204
    issue = EquipmentIssue.all_companies.filter(description="Le clavier ne répond plus").get()
    assert Notification.all_companies.filter(
        recipient=company_a.hr, text__contains="signale un problème"
    ).exists()
    hr = client_for(company_a.hr)
    assert hr.post(f"/materiel/signalements/{issue.pk}/reparation/").status_code == 204
    item = reload(held)
    assert item.status == "repair" and item.holder_id == company_a.employee.pk  # conservé
    missing = hr.post(f"/materiel/signalements/{issue.pk}/clore/", {"resolution": ""})
    assert "Indiquez la résolution." in missing.content.decode()
    assert (
        hr.post(
            f"/materiel/signalements/{issue.pk}/clore/", {"resolution": "Clavier remplacé"}
        ).status_code
        == 204
    )
    assert hr.post(f"/materiel/parc/{held.public_id}/fin-reparation/").status_code == 204
    assert reload(held).status == "assigned"  # rendu à son détenteur


def test_equipment_request_is_validated_by_hr_then_linked_to_an_item(client_for, company_a):
    employee = client_for(company_a.employee)
    assert (
        employee.post(
            "/materiel/nouvelle/", {"kind": "screen", "reason": "Deuxième écran"}
        ).status_code
        == 204
    )
    request = EquipmentRequest.all_companies.filter(reason="Deuxième écran", status="pending").get()
    manager = client_for(company_a.manager)
    assert manager.post(f"/materiel/{request.public_id}/valider/").status_code in (403, 404, 409)
    hr = client_for(company_a.hr)
    assert "Deuxième écran" in hr.get("/materiel/?onglet=demandes").content.decode()
    assert hr.post(f"/materiel/{request.public_id}/valider/").status_code == 204
    assert "Attribuer un équipement" in hr.get("/materiel/?onglet=demandes").content.decode()
    stock = company_a.requests["stock_item"]  # écran en stock
    url = f"/materiel/demandes/{request.public_id}/attribuer/"
    assert hr.post(url, {"item": stock.pk}).status_code == 204
    assignment = EquipmentAssignment.all_companies.get(item=stock, returned_at__isnull=True)
    assert assignment.request_id == request.pk and assignment.employee_id == company_a.employee.pk
    with tenant_context(company_a.company):
        other = EquipmentItem.objects.create(kind="screen", model="x", serial_number="SCR-2")
    twice = hr.post(url, {"item": other.pk})
    assert twice.status_code == 409


def test_manager_sees_the_team_equipment_read_only(client_for, company_a):
    content = client_for(company_a.manager).get("/materiel/?onglet=equipe").content.decode()
    assert company_a.requests["item"].serial_number in content
    assert "Restituer" not in content and "Attribuer" not in content


def test_archiving_a_holder_alerts_hr(client_for, company_a):
    admin = client_for(company_a.admin)
    url = f"/annuaire/{company_a.employee.public_id}/archiver/"
    modal = admin.get(url).content.decode()
    assert "Cette personne détient encore 1 équipement." in modal
    assert company_a.requests["item"].serial_number in modal
    response = admin.post(url, {"departure_date": timezone.localdate().isoformat()})
    assert response.status_code == 204
    note = Notification.all_companies.get(recipient=company_a.hr, text__contains="est archivé")
    assert company_a.requests["item"].serial_number in note.text
    assert reload(company_a.requests["item"]).holder_id == company_a.employee.pk  # non bloqué


def test_actions_are_logged_and_traced(client_for, company_a):
    stock = company_a.requests["stock_item"]
    client_for(company_a.hr).post(
        f"/materiel/parc/{stock.public_id}/attribuer/", {"employee": company_a.manager.pk}
    )
    assert AuditLog.all_companies.filter(action="equipment.assigned").exists()
    assert EquipmentEvent.all_companies.filter(item=stock, action="assigned").exists()


def test_undo_token_of_another_company_is_refused(client_for, company_a, company_b):
    stock = company_a.requests["stock_item"]
    response = client_for(company_a.hr).post(
        f"/materiel/parc/{stock.public_id}/attribuer/", {"employee": company_a.manager.pk}
    )
    undo_url = toast(response)["undo_url"]
    assert client_for(company_b.hr).post(undo_url).status_code == 409
    assert reload(stock).status == "assigned"


def test_new_person_assignment_choices_are_in_post_people_of_the_company(
    client_for, company_a, company_b
):
    with tenant_context(company_a.company):
        left = EmployeeFactory(company=company_a.company, status="left", last_name="Partie")
    modal = (
        client_for(company_a.hr)
        .get(f"/materiel/parc/{company_a.requests['stock_item'].public_id}/attribuer/")
        .content.decode()
    )
    assert left.last_name not in modal and company_b.employee.last_name not in modal
