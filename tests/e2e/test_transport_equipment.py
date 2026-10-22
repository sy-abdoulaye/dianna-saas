"""Parcours du lot 5 : justificatif de transport déposé puis validé par les RH (aperçu du
fichier) ; matériel attribué puis « Annuler » depuis la notification visuelle."""

import re

import pytest
from playwright.sync_api import expect

from conftest import PDF_BYTES
from tests.e2e.test_requests import sign_in

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def urls(live_server):
    port = live_server.url.rsplit(":", 1)[1]
    return lambda path="/": f"http://exemple.localhost:{port}{path}"


def test_employee_uploads_a_proof_and_hr_validates_it(browser, urls, company_a, tmp_path):
    proof = tmp_path / "abonnement.pdf"
    proof.write_bytes(PDF_BYTES)
    employee = browser.new_context(locale="fr-FR")
    page = employee.new_page()
    sign_in(page, urls, company_a.employee)
    page.goto(urls("/transport/"))
    expect(page.get_by_text("article L3261-2 du Code du travail")).to_be_visible()
    page.get_by_role("button", name="Ajouter un justificatif").click()
    dialog = page.locator("dialog[open]")
    # Montant saisi avec une virgule (L5-20) : enregistré 2,15 €.
    dialog.get_by_label("Montant payé (€)").fill("2,15")
    dialog.locator("input[type=file]").set_input_files(str(proof))
    dialog.get_by_role("button", name="Envoyer la demande").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("transmise aux RH")
    employee.close()
    from apps.approvals.models import TransportProof

    saved = TransportProof.all_companies.filter(requester=company_a.employee).latest("pk")
    assert str(saved.amount) == "2.15"

    hr = browser.new_context(locale="fr-FR", accept_downloads=True)
    page = hr.new_page()
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/transport/?onglet=a-valider"))
    from django.utils import timezone, translation

    from apps.core.dates import format_date

    with translation.override("fr"):
        month = format_date(timezone.localdate(), "month")
    # Résumé dans l'ordre du prototype : mois · type · montant · nom du fichier.
    summary = re.compile(f"{month} · Abonnement mensuel · 2,15\\s€ · abonnement.pdf")
    page.get_by_role("button", name=summary).click()
    dialog = page.locator("dialog[open]")
    expect(dialog.get_by_text("abonnement.pdf").first).to_be_visible()
    expect(dialog.get_by_text("2,15\u00a0€").first).to_be_visible()
    with page.expect_download() as info:
        dialog.get_by_role("link", name="Télécharger").click()
    assert info.value.suggested_filename == "abonnement.pdf"
    dialog.get_by_role("button", name="Valider").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Demande validée")
    hr.close()


def test_hr_assigns_an_item_then_undoes_it(page, urls, company_a, console_errors):
    stock = company_a.requests["stock_item"]
    sign_in(page, urls, company_a.hr)
    page.goto(urls("/materiel/?onglet=parc"))
    row = page.locator("tbody tr", has_text=stock.serial_number)
    row.get_by_role("button", name="Attribuer").click()
    dialog = page.locator("dialog[open]")
    dialog.get_by_label("Collaborateur").select_option(str(company_a.manager.pk))
    dialog.get_by_role("button", name="Attribuer").click()
    toast = page.locator("#toasts .toast").last
    expect(toast).to_contain_text("Équipement attribué")
    expect(page.locator("tbody tr", has_text=stock.serial_number)).to_contain_text("Attribué")
    toast.get_by_role("button", name="Annuler").click()
    expect(page.locator("#toasts .toast").last).to_contain_text("Attribution annulée")
    expect(page.locator("tbody tr", has_text=stock.serial_number)).to_contain_text("En stock")
    assert console_errors == []
