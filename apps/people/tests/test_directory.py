"""Annuaire : critères d'acceptation de docs/modules/03-annuaire.md, permissions, erreurs."""

import json
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.models import User
from apps.core.context import ActionContext
from apps.core.models import AuditLog
from apps.core.tenancy import tenant_context
from apps.core.tests.test_files import bomb_png
from apps.people import services
from apps.people.models import Employee, EmployeeChange, EmployeeStatus, Role
from apps.people.tests.conftest import image_bytes
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db


def detail_url(person):
    return f"/annuaire/{person.public_id}/"


def form_data(company_data, **overrides):
    data = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada.lovelace@exemple.fr",
        "job_title": "Analyste",
        "service": company_data.service.pk,
        "site": company_data.site.pk,
        "arrival_date": "2024-01-08",
        "contract_type": "cdi",
        "work_time": "full_35",
    }
    data.update(overrides)
    return data


# ---------- Liste ----------


def test_employee_sees_no_status_no_left_people_no_hr_info(client_for, company_a):
    EmployeeFactory(
        company=company_a.company,
        user=None,
        last_name="Partie",
        status="left",
        registration_number="MAT-SECRET",
    )
    content = client_for(company_a.employee).get("/annuaire/", follow=True).content.decode()
    assert "Les informations RH (contrat, matricule) ne sont pas affichées." in content
    assert ">Statut<" not in content
    assert "Partie" not in content
    assert "MAT-SECRET" not in content


def test_hr_sees_status_and_actions(client_for, company_a):
    content = client_for(company_a.hr).get("/annuaire/", follow=True).content.decode()
    assert ">Statut<" in content
    assert "Ajouter un collaborateur" in content
    assert f"Archiver {company_a.employee.full_name}" in content


def test_upcoming_arrivals_are_visible_and_counted_in_post(client_for, company_a):
    EmployeeFactory(
        company=company_a.company, user=None, last_name="Arrivante", status=EmployeeStatus.UPCOMING
    )
    content = client_for(company_a.employee).get("/annuaire/", follow=True).content.decode()
    assert "Arrivante" in content
    assert "Arrivée prochaine" in content
    hr = client_for(company_a.hr).get("/annuaire/?statut=en_poste", follow=True).content.decode()
    assert "Arrivante" in hr


def test_hr_filters_left_people(client_for, company_a):
    EmployeeFactory(company=company_a.company, user=None, last_name="Partie", status="left")
    content = client_for(company_a.hr).get("/annuaire/?statut=partis", follow=True).content.decode()
    assert "Partie" in content and company_a.employee.last_name not in content


def test_search_without_result_shows_the_empty_state(client_for, company_a):
    content = client_for(company_a.employee).get("/annuaire/?q=zzzz", follow=True).content.decode()
    assert "Aucun collaborateur trouvé" in content
    assert "Aucune fiche ne correspond à « zzzz »" in content
    assert "Réinitialiser les filtres" in content


def test_filters_and_page_live_in_the_url_and_htmx_returns_the_fragment(client_for, company_a):
    client = client_for(company_a.employee)
    url = f"/annuaire/?q={company_a.manager.last_name}&page=1&vue=liste"
    full = client.get(url).content.decode()
    assert "<html" in full and company_a.manager.full_name in full
    fragment = client.get(url, headers={"HX-Request": "true", "HX-Target": "results"})
    content = fragment.content.decode()
    assert "<html" not in content and company_a.manager.full_name in content
    assert company_a.employee.full_name not in content


def test_directory_address_always_carries_the_view(client_for, company_a):
    client = client_for(company_a.employee)
    first = client.get("/annuaire/?q=dupont")
    assert first.status_code == 302 and first["Location"] == "/annuaire/?q=dupont&vue=liste"
    client.get("/annuaire/?vue=cartes")
    remembered = client.get("/annuaire/?vue=inconnue&page=2")
    assert remembered["Location"] == "/annuaire/?vue=cartes&page=2"
    content = client.get("/annuaire/?vue=cartes&q=zzzz").content.decode()
    assert 'href="/annuaire/?vue=cartes"' in content  # Réinitialiser garde l'affichage


def test_cards_view_is_remembered_and_shows_12_per_page(client_for, company_a):
    for index in range(14):
        EmployeeFactory(company=company_a.company, user=None, last_name=f"Zz{index:02d}")
    client = client_for(company_a.employee)
    content = client.get("/annuaire/?vue=cartes").content.decode()
    assert "1 à 12 sur" in content and "person-card" in content
    assert "person-card" in client.get("/annuaire/", follow=True).content.decode()  # mémorisé
    assert "1 à 8 sur" in client.get("/annuaire/?vue=liste").content.decode()


def test_global_search_suggests_five_people_at_most(client_for, company_a):
    for index in range(7):
        EmployeeFactory(
            company=company_a.company, user=None, first_name="Zoé", last_name=f"N{index}"
        )
    content = client_for(company_a.employee).get("/annuaire/suggestions/?q=Zo").content.decode()
    import re

    assert len(re.findall(r'href="/annuaire/[0-9a-f-]{36}/"', content)) == 5
    assert "Voir tous les résultats dans l'annuaire" in content


# ---------- Fiche ----------


def test_colleague_detail_hides_hr_information_in_the_html(client_for, company_a):
    Employee.all_companies.filter(pk=company_a.manager.pk).update(registration_number="MAT-42")
    content = client_for(company_a.employee).get(detail_url(company_a.manager)).content.decode()
    assert "Coordonnées professionnelles" in content
    assert "Informations RH" not in content and "MAT-42" not in content


def test_manager_sees_team_contacts_but_not_their_hr_information(client_for, company_a):
    # V-07 : même pour son équipe, pas d'informations RH.
    Employee.all_companies.filter(pk=company_a.employee.pk).update(registration_number="MAT-7")
    content = client_for(company_a.manager).get(detail_url(company_a.employee)).content.decode()
    assert company_a.employee.email in content
    assert "MAT-7" not in content


def test_self_sees_own_hr_information(client_for, company_a):
    content = client_for(company_a.employee).get(detail_url(company_a.employee)).content.decode()
    assert "Visible par vous et les RH" in content
    assert "C&#x27;est vous" in content or "C'est vous" in content
    assert "Modifier mes coordonnées" in content


def test_hr_sees_hr_information_and_history(client_for, company_a):
    client = client_for(company_a.hr)
    assert "Réservé aux RH" in client.get(detail_url(company_a.employee)).content.decode()
    history = client.get(detail_url(company_a.employee) + "?onglet=historique").content.decode()
    assert "Historique" in history and "Fiche modifiée" in history


def test_history_tab_is_reserved_to_hr(client_for, company_a):
    content = (
        client_for(company_a.manager)
        .get(detail_url(company_a.employee) + "?onglet=historique")
        .content.decode()
    )
    assert "Fiche modifiée" not in content


def test_team_tab_lists_direct_reports(client_for, company_a):
    content = (
        client_for(company_a.employee)
        .get(detail_url(company_a.manager) + "?onglet=equipe")
        .content.decode()
    )
    assert company_a.employee.full_name in content


def test_left_record_is_404_for_employees_and_visible_to_hr(client_for, company_a):
    left = EmployeeFactory(company=company_a.company, user=None, status="left")
    assert client_for(company_a.employee).get(detail_url(left)).status_code == 404
    assert client_for(company_a.hr).get(detail_url(left)).status_code == 200


# ---------- Création et modification ----------


def test_only_hr_and_admin_can_create(client_for, company_a):
    assert client_for(company_a.employee).get("/annuaire/nouveau/").status_code == 403
    assert client_for(company_a.manager).get("/annuaire/nouveau/").status_code == 403
    page = client_for(company_a.hr).get("/annuaire/nouveau/").content.decode()
    assert "Nouveau collaborateur" in page
    assert "Profil d&#x27;accès" not in page  # réservé à l'administrateur
    admin_page = client_for(company_a.admin).get("/annuaire/nouveau/").content.decode()
    assert "Envoyer une invitation par e-mail" in admin_page


def test_duplicate_email_shows_the_error_and_keeps_the_input(client_for, company_a):
    response = client_for(company_a.hr).post(
        "/annuaire/nouveau/",
        form_data(company_a, email=company_a.manager.email.upper(), job_title="Saisie conservée"),
    )
    assert response.status_code == 422
    content = response.content.decode()
    assert f"Cette adresse est déjà utilisée par {company_a.manager.full_name}." in content
    assert "1 information est à corriger." in content
    assert 'value="Saisie conservée"' in content
    assert 'aria-invalid="true"' in content


def test_required_fields(client_for, company_a):
    response = client_for(company_a.hr).post("/annuaire/nouveau/", {})
    content = response.content.decode()
    assert "7 informations sont à corriger." in content
    assert content.count("Ce champ est obligatoire.") == 7


def test_creating_records_history_and_audit(client_for, company_a):
    response = client_for(company_a.hr).post("/annuaire/nouveau/", form_data(company_a))
    assert response.status_code == 302
    with tenant_context(company_a.company):
        ada = Employee.objects.get(email="ada.lovelace@exemple.fr")
        assert ada.status == EmployeeStatus.ACTIVE and ada.user is None
        assert EmployeeChange.objects.filter(employee=ada, kind="created").exists()
        assert AuditLog.objects.filter(action="people.created", actor=company_a.hr).exists()


def test_future_arrival_means_upcoming(client_for, company_a):
    future = (timezone.localdate() + timedelta(days=20)).isoformat()
    client_for(company_a.hr).post("/annuaire/nouveau/", form_data(company_a, arrival_date=future))
    assert Employee.all_companies.get(email="ada.lovelace@exemple.fr").status == "upcoming"


def test_admin_creates_with_role_and_invitation(client_for, company_a, run_tasks):
    client_for(company_a.admin).post(
        "/annuaire/nouveau/", form_data(company_a, role=Role.HR, invite="on")
    )
    ada = Employee.all_companies.get(email="ada.lovelace@exemple.fr")
    assert ada.role == Role.HR
    run_tasks()
    assert mail.outbox[-1].to == ["ada.lovelace@exemple.fr"]


def test_editing_records_only_field_names(client_for, company_a):
    client = client_for(company_a.hr)
    data = form_data(
        company_a,
        first_name=company_a.employee.first_name,
        last_name=company_a.employee.last_name,
        email=company_a.employee.email,
        job_title="Conseillère senior",
        manager=company_a.manager.pk,
    )
    response = client.post(f"/annuaire/{company_a.employee.public_id}/modifier/", data)
    assert response.status_code == 302
    with tenant_context(company_a.company):
        change = EmployeeChange.objects.filter(employee=company_a.employee).first()
    assert "job_title" in change.fields
    assert "Conseillère senior" not in json.dumps(change.fields)


def test_manager_loop_is_refused(client_for, company_a):
    data = form_data(
        company_a,
        first_name="Louise",
        last_name=company_a.manager.last_name,
        email=company_a.manager.email,
        manager=company_a.employee.pk,
    )
    response = client_for(company_a.hr).post(
        f"/annuaire/{company_a.manager.public_id}/modifier/", data
    )
    assert "Ce choix créerait une boucle dans la hiérarchie." in response.content.decode()


def test_last_admin_cannot_be_demoted_from_the_record(client_for, company_a):
    admin = company_a.admin
    data = form_data(
        company_a,
        first_name=admin.first_name,
        last_name=admin.last_name,
        email=admin.email,
        role=Role.EMPLOYEE,
    )
    other_admin = EmployeeFactory(company=company_a.company, role=Role.HR, user=None)
    response = client_for(admin).post(
        f"/annuaire/{other_admin.public_id}/modifier/",
        form_data(company_a, first_name="X", last_name="Y", email=other_admin.email, role=Role.HR),
    )
    assert response.status_code == 302
    # Admin unique de l'entreprise : se rétrograder lui-même par une autre fiche admin ? Non :
    # on rétrograde l'unique administrateur depuis le compte d'un autre administrateur.
    second = EmployeeFactory(company=company_a.company, role=Role.ADMIN)
    response = client_for(second).post(f"/annuaire/{admin.public_id}/modifier/", data)
    assert response.status_code == 302  # il reste « second »
    Employee.all_companies.filter(pk=second.pk).update(role=Role.HR)
    # Administrateur unique : personne ne peut le rétrograder, même hors requête (service).
    third = EmployeeFactory(company=company_a.company, role=Role.ADMIN)
    Employee.all_companies.filter(company=company_a.company, role=Role.ADMIN).exclude(
        pk=third.pk
    ).update(role=Role.HR)
    with tenant_context(company_a.company), pytest.raises(services.PeopleError) as error:
        services.update_employee(third, {"role": Role.EMPLOYEE}, context=ActionContext(None))
    assert "dernier administrateur actif" in str(error.value.message)


def own_form_data(company_data, person, **overrides):
    return form_data(
        company_data,
        first_name=person.first_name,
        last_name=person.last_name,
        email=person.email,
        **overrides,
    )


def test_own_role_field_is_not_shown_and_cannot_be_forged(client_for, company_a):
    admin = company_a.admin
    EmployeeFactory(company=company_a.company, role=Role.ADMIN)  # pas le dernier admin
    client = client_for(admin)
    page = client.get(f"/annuaire/{admin.public_id}/modifier/").content.decode()
    assert 'name="role"' not in page and "Accès à Dianna" not in page
    other = client.get(f"/annuaire/{company_a.employee.public_id}/modifier/").content.decode()
    assert 'name="role"' in other  # le champ existe bien pour les autres fiches
    response = client.post(
        f"/annuaire/{admin.public_id}/modifier/", own_form_data(company_a, admin, role="employee")
    )
    assert response.status_code == 302
    assert Employee.all_companies.get(pk=admin.pk).role == Role.ADMIN


def test_update_employee_refuses_a_change_of_ones_own_role(company_a):
    admin = company_a.admin
    EmployeeFactory(company=company_a.company, role=Role.ADMIN)
    with tenant_context(company_a.company), pytest.raises(services.PeopleError) as error:
        services.update_employee(admin, {"role": Role.EMPLOYEE}, context=ActionContext(admin))
    assert str(error.value.message) == "Vous ne pouvez pas modifier votre propre profil."
    assert Employee.all_companies.get(pk=admin.pk).role == Role.ADMIN


def role_changes(company_data):
    with tenant_context(company_data.company):
        return list(
            AuditLog.objects.filter(action="people.role_changed").values_list("summary", flat=True)
        )


def test_role_change_from_the_record_goes_through_change_role(client_for, company_a):
    target = company_a.employee
    response = client_for(company_a.admin).post(
        f"/annuaire/{target.public_id}/modifier/", own_form_data(company_a, target, role="hr")
    )
    assert response.status_code == 302
    assert Employee.all_companies.get(pk=target.pk).role == Role.HR
    assert role_changes(company_a) == [
        f"Profil de {target.full_name} : Salarié → Ressources humaines"
    ]
    with tenant_context(company_a.company):
        kinds = list(target.changes.values_list("kind", flat=True))
    assert EmployeeChange.Kind.ROLE in kinds


def test_profile_given_at_creation_is_logged_as_a_role_change(client_for, company_a):
    response = client_for(company_a.admin).post(
        "/annuaire/nouveau/", form_data(company_a, role="admin", invite="")
    )
    assert response.status_code == 302
    created = Employee.all_companies.get(company=company_a.company, email="ada.lovelace@exemple.fr")
    assert created.role == Role.ADMIN
    assert role_changes(company_a) == ["Profil de Ada Lovelace : Salarié → Administrateur"]


# ---------- Photo ----------


def test_photo_given_at_creation_is_stored_under_the_company_and_shown(
    client_for, company_a, settings
):
    client = client_for(company_a.hr)
    photo = SimpleUploadedFile("moi.png", image_bytes(), content_type="image/png")
    response = client.post("/annuaire/nouveau/", form_data(company_a, photo_upload=photo))
    assert response.status_code == 302
    created = Employee.all_companies.get(company=company_a.company, email="ada.lovelace@exemple.fr")
    assert created.photo.name.startswith(f"{company_a.company.pk}/photos/")
    root = settings.PRIVATE_MEDIA_ROOT
    assert not (root / "None").exists()
    page = client.get(response["Location"]).content.decode()
    url = page.split('<img src="')[1].split('"')[0]
    served = client.get(url)
    assert served.status_code == 200 and served["Content-Type"] == "image/png"


def test_photo_path_never_uses_an_unknown_company(db):
    from apps.core.tenancy import NoCurrentCompanyError
    from apps.people.models import employee_photo_path

    with pytest.raises(NoCurrentCompanyError):
        employee_photo_path(Employee(first_name="A", last_name="B"), "x.png")


def test_photo_is_reencoded_and_served_by_a_signed_url(client_for, company_a, company_b):
    client = client_for(company_a.hr)
    photo = SimpleUploadedFile("moi.png", image_bytes(), content_type="image/png")
    data = form_data(
        company_a,
        first_name=company_a.employee.first_name,
        last_name=company_a.employee.last_name,
        email=company_a.employee.email,
        photo_upload=photo,
    )
    assert (
        client.post(f"/annuaire/{company_a.employee.public_id}/modifier/", data).status_code == 302
    )
    page = client.get(detail_url(company_a.employee)).content.decode()
    url = page.split('<img src="')[1].split('"')[0]
    assert url.startswith("/fichiers/")
    response = client.get(url)
    assert response.status_code == 200 and response["Content-Type"] == "image/png"
    assert response["Cache-Control"] == "private, max-age=300"
    # Même URL sur l'hôte d'une autre entreprise : refusée.
    other = client_for(company_b.employee).get(url)
    assert other.status_code == 404


def test_private_file_is_refused_on_another_company_host(client_for, company_a, company_b):
    test_photo_is_reencoded_and_served_by_a_signed_url(client_for, company_a, company_b)


def test_photo_url_expires(client_for, company_a, settings):
    client = client_for(company_a.hr)
    photo = SimpleUploadedFile("moi.png", image_bytes(), content_type="image/png")
    client.post(
        f"/annuaire/{company_a.employee.public_id}/modifier/",
        form_data(
            company_a,
            first_name="C",
            last_name="D",
            email=company_a.employee.email,
            photo_upload=photo,
        ),
    )
    url = (
        client.get(detail_url(company_a.employee))
        .content.decode()
        .split('<img src="')[1]
        .split('"')[0]
    )
    settings.PRIVATE_FILE_URL_SECONDS = -1
    assert client.get(url).status_code == 404


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("virus.exe", b"MZ\x90\x00", "Choisissez une image JPG ou PNG."),
        ("grande.png", image_bytes() + b"0" * (2 * 1024 * 1024), "Le fichier dépasse 2 Mo."),
        ("bombe.png", bomb_png(), "Image trop grande."),
    ],
)
def test_invalid_photos_are_refused(client_for, company_a, name, content, message):
    upload = SimpleUploadedFile(name, content)
    response = client_for(company_a.hr).post(
        "/annuaire/nouveau/", form_data(company_a, photo_upload=upload)
    )
    assert response.status_code == 422
    assert message in response.content.decode()


# ---------- Archivage ----------


def test_hr_cannot_archive_an_administrator(client_for, company_a):
    EmployeeFactory(company=company_a.company, role=Role.ADMIN)  # pas le dernier admin
    admin = company_a.admin
    client = client_for(company_a.hr)
    detail = client.get(detail_url(admin)).content.decode()
    assert f"/annuaire/{admin.public_id}/archiver/" not in detail
    listing = client.get("/annuaire/", follow=True).content.decode()
    assert f"/annuaire/{admin.public_id}/archiver/" not in listing
    assert f"/annuaire/{company_a.employee.public_id}/archiver/" in listing
    response = client.post(
        f"/annuaire/{admin.public_id}/archiver/",
        {"departure_date": timezone.localdate().isoformat()},
    )
    assert response.status_code == 422
    assert "Seul un administrateur peut archiver un administrateur." in response.content.decode()
    refreshed = Employee.all_companies.get(pk=admin.pk)
    assert refreshed.status == EmployeeStatus.ACTIVE and refreshed.user.is_active


def test_an_administrator_can_archive_another_administrator(client_for, company_a):
    other = EmployeeFactory(company=company_a.company, role=Role.ADMIN)
    client = client_for(company_a.admin)
    assert (
        f"/annuaire/{other.public_id}/archiver/" in client.get(detail_url(other)).content.decode()
    )
    response = client.post(
        f"/annuaire/{other.public_id}/archiver/",
        {"departure_date": timezone.localdate().isoformat()},
    )
    assert response.status_code == 204
    assert Employee.all_companies.get(pk=other.pk).status == EmployeeStatus.LEFT


def test_archive_then_undo_restores_active(client_for, company_a):
    client = client_for(company_a.hr)
    url = f"/annuaire/{company_a.employee.public_id}/archiver/"
    modal = client.get(url).content.decode()
    assert "Archiver la fiche" in modal and 'type="date"' in modal
    response = client.post(url, {"departure_date": timezone.localdate().isoformat()})
    assert response.status_code == 204
    payload = json.loads(response["HX-Trigger"])
    assert payload["toast"]["title"] == "Fiche archivée"
    assert payload["peopleChanged"] is True
    employee = Employee.all_companies.get(pk=company_a.employee.pk)
    assert employee.status == "left" and not employee.user.is_active
    # Le compte désactivé ne peut plus naviguer.
    assert client_for(company_a.employee).get("/").status_code == 302
    undo = client.post(payload["toast"]["undo_url"])
    assert json.loads(undo["HX-Trigger"])["toast"]["title"] == "Archivage annulé"
    employee.refresh_from_db()
    employee.user.refresh_from_db()
    assert employee.status == "active" and employee.user.is_active
    assert employee.departure_date is None


def test_undo_archive_of_another_company_is_refused(client_for, company_a, company_b):
    response = client_for(company_a.hr).post(
        f"/annuaire/{company_a.employee.public_id}/archiver/",
        {"departure_date": timezone.localdate().isoformat()},
    )
    undo_url = json.loads(response["HX-Trigger"])["toast"]["undo_url"]
    # Jeton lié à son auteur : un RH de l'autre entreprise ne peut pas l'utiliser.
    assert client_for(company_b.hr).post(undo_url).status_code == 409


def test_reactivate(client_for, company_a):
    Employee.all_companies.filter(pk=company_a.employee.pk).update(status="left")
    User.objects.filter(pk=company_a.employee.user_id).update(is_active=False)
    response = client_for(company_a.hr).post(f"/annuaire/{company_a.employee.public_id}/reactiver/")
    assert json.loads(response["HX-Trigger"])["toast"]["title"] == "Fiche réactivée"
    assert User.objects.get(pk=company_a.employee.user_id).is_active


def test_hr_cannot_archive_themselves_nor_the_last_admin(client_for, company_a):
    client = client_for(company_a.hr)
    today = timezone.localdate().isoformat()
    own = client.post(f"/annuaire/{company_a.hr.public_id}/archiver/", {"departure_date": today})
    assert "Vous ne pouvez pas archiver votre propre fiche." in own.content.decode()
    admin = client.post(
        f"/annuaire/{company_a.admin.public_id}/archiver/", {"departure_date": today}
    )
    assert "Seul un administrateur peut archiver un administrateur." in admin.content.decode()
    # Le dernier administrateur reste protégé, même hors requête (plateforme, commande).
    with tenant_context(company_a.company), pytest.raises(services.PeopleError) as error:
        services.archive(company_a.admin, context=ActionContext(None))
    assert "dernier administrateur actif" in str(error.value.message)


def test_employees_cannot_archive(client_for, company_a):
    response = client_for(company_a.employee).post(
        f"/annuaire/{company_a.manager.public_id}/archiver/", {"departure_date": "2026-10-19"}
    )
    assert response.status_code == 403


# ---------- Mes coordonnées ----------


def test_employee_edits_only_phone_and_office(client_for, company_a):
    client = client_for(company_a.employee)
    bad = client.post("/annuaire/mes-coordonnees/", {"phone": "12", "office": ""})
    assert bad.status_code == 422
    assert "Saisissez un numéro valide (au moins 8 chiffres)." in bad.content.decode()
    ok = client.post(
        "/annuaire/mes-coordonnees/",
        {"phone": "04 72 00 00 00", "office": "B204", "job_title": "Directrice"},
    )
    assert ok.status_code == 204
    employee = Employee.all_companies.get(pk=company_a.employee.pk)
    assert employee.phone == "04 72 00 00 00" and employee.office == "B204"
    assert employee.job_title != "Directrice"
    assert client.get(f"/annuaire/{company_a.employee.public_id}/modifier/").status_code == 403


# ---------- Import CSV ----------

HEADER = "prenom;nom;email;poste;service;site;manager_email;date_arrivee;contrat\n"


def upload(text, encoding="utf-8"):
    return SimpleUploadedFile("salaries.csv", text.encode(encoding), content_type="text/csv")


def test_import_is_reserved_to_admin(client_for, company_a):
    assert client_for(company_a.hr).get("/annuaire/import/").status_code == 403
    assert client_for(company_a.admin).get("/annuaire/import/").status_code == 200


def test_import_preview_then_confirm(client_for, company_a):
    client = client_for(company_a.admin)
    text = (
        HEADER
        + "Jean;Neuf;jean.neuf@exemple.fr;Comptable;Finance;Lyon;"
        + f"{company_a.manager.email};03/11/2025;CDI\n"
        + "Lina;Neuve;lina.neuve@exemple.fr;Comptable;Finance;Lyon;"
        + "jean.neuf@exemple.fr;2025-11-03;Stage\n"
    )
    preview = client.post("/annuaire/import/", {"step": "upload", "file": upload(text)})
    content = preview.content.decode()
    assert "2 fiches prêtes à être importées." in content
    assert "services Finance" in content
    token = content.split('name="token" value="')[1].split('"')[0]
    done = client.post("/annuaire/import/", {"step": "confirm", "token": token})
    assert done.status_code == 302
    with tenant_context(company_a.company):
        lina = Employee.objects.get(email="lina.neuve@exemple.fr")
        assert lina.manager.email == "jean.neuf@exemple.fr"
        assert lina.service.name == "Finance" and lina.contract_type == "internship"
        assert AuditLog.objects.filter(action="people.imported").exists()


def test_import_errors_block_every_line(client_for, company_a):
    text = (
        HEADER
        + "Jean;Neuf;jean.neuf@exemple.fr;Comptable;Finance;Lyon;;03/11/2025;CDI\n"
        + f"Dup;Licate;{company_a.employee.email};Poste;Support client;Lyon;;31/02/2025;Freelance\n"
    )
    content = (
        client_for(company_a.admin)
        .post("/annuaire/import/", {"step": "upload", "file": upload(text)})
        .content.decode()
    )
    assert "1 ligne contient des erreurs bloquantes." in content
    assert "Cette adresse est déjà utilisée dans l&#x27;annuaire." in content
    assert "Date d&#x27;arrivée invalide (JJ/MM/AAAA)." in content
    assert "Contrat inconnu" in content
    assert 'name="token"' not in content
    assert not Employee.all_companies.filter(email="jean.neuf@exemple.fr").exists()


def test_import_accepts_excel_encoding_and_checks_columns(client_for, company_a):
    client = client_for(company_a.admin)
    text = (
        HEADER + "Hélène;Béranger;helene.b@exemple.fr;Comptable;Support client;Lyon;;03/11/2025;\n"
    )
    content = client.post(
        "/annuaire/import/", {"step": "upload", "file": upload(text, "cp1252")}
    ).content.decode()
    assert "Béranger" in content and "1 fiche prête à être importée." in content
    bad = client.post("/annuaire/import/", {"step": "upload", "file": upload("nom;prenom\nA;B\n")})
    assert "Colonnes manquantes" in bad.content.decode()


@pytest.mark.parametrize(
    "data",
    [{"step": "confirm", "token": "faux"}, {"step": "confirm"}, {"step": "confirm", "token": ""}],
    ids=["mauvais-jeton", "sans-jeton", "jeton-vide"],
)
def test_import_confirmation_without_a_matching_preview_restarts(client_for, company_a, data):
    client = client_for(company_a.admin)
    done = client.post("/annuaire/import/", data)
    assert done.status_code == 302 and done["Location"] == "/annuaire/import/"
    page = client.get(done["Location"]).content.decode()
    assert "L&#x27;import a expiré. Recommencez." in page


def test_import_confirmation_with_htmx_uses_the_common_bricks(client_for, company_a):
    client = client_for(company_a.admin)
    expired = client.post(
        "/annuaire/import/", {"step": "confirm", "token": "faux"}, headers={"HX-Request": "true"}
    )
    assert expired.status_code == 409
    assert json.loads(expired["HX-Location"])["path"] == "/annuaire/import/"
    assert json.loads(expired["HX-Trigger"])["toast"] == {
        "title": "L'import a expiré. Recommencez.",
        "kind": "err",
    }
    text = HEADER + "Jean;Neuf;jean.neuf@exemple.fr;Comptable;Finance;Lyon;;03/11/2025;CDI\n"
    preview = client.post("/annuaire/import/", {"step": "upload", "file": upload(text)})
    content = preview.content.decode()
    assert 'hx-post="/annuaire/import/"' in content
    token = content.split('name="token" value="')[1].split('"')[0]
    done = client.post(
        "/annuaire/import/", {"step": "confirm", "token": token}, headers={"HX-Request": "true"}
    )
    assert done.status_code == 204
    assert json.loads(done["HX-Location"])["path"] == "/annuaire/"


def test_import_confirmation_with_an_emptied_session_restarts(client_for, company_a):
    client = client_for(company_a.admin)
    text = HEADER + "Jean;Neuf;jean.neuf@exemple.fr;Comptable;Finance;Lyon;;03/11/2025;CDI\n"
    content = client.post("/annuaire/import/", {"step": "upload", "file": upload(text)})
    token = content.content.decode().split('name="token" value="')[1].split('"')[0]
    session = client.session
    session["people_import"] = {"token": token}  # aperçu incomplet
    session.save()
    done = client.post("/annuaire/import/", {"step": "confirm", "token": token})
    assert done.status_code == 302 and done["Location"] == "/annuaire/import/"
    assert not Employee.all_companies.filter(email="jean.neuf@exemple.fr").exists()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (
            (HEADER + "Jean;" + "x" * 140_000 + ";a@exemple.fr;P;S;L;;03/11/2025;\n").encode(),
            "Ligne 2 : le fichier n&#x27;est pas un CSV valide",
        ),
        (
            (HEADER + "Je\x00an;Neuf;a@exemple.fr;P;S;L;;03/11/2025;\n").encode(),
            "Le fichier n&#x27;est pas lisible. Enregistrez-le en CSV UTF-8.",
        ),
        (
            HEADER.encode() + b"Jean;N\x81\x8d;a@exemple.fr;P;S;L;;03/11/2025;\n",
            "Le fichier n&#x27;est pas lisible. Enregistrez-le en CSV UTF-8.",
        ),
        (
            "prenom;nom\n".encode("utf-16"),
            "Le fichier n&#x27;est pas lisible. Enregistrez-le en CSV UTF-8.",
        ),
    ],
    ids=["champ-trop-long-pour-csv", "octet-nul", "mauvais-encodage", "utf-16"],
)
def test_malformed_import_files_give_a_clear_message(client_for, company_a, raw, message):
    file = SimpleUploadedFile("salaries.csv", raw, content_type="text/csv")
    response = client_for(company_a.admin).post(
        "/annuaire/import/", {"step": "upload", "file": file}
    )
    assert response.status_code == 422
    assert message in response.content.decode()


def test_import_checks_field_lengths_with_the_line_number(client_for, company_a):
    text = (
        HEADER
        + "Jean;Neuf;jean.neuf@exemple.fr;Comptable;Finance;Lyon;;03/11/2025;CDI\n"
        + f"{'P' * 61};Long;long@exemple.fr;{'Q' * 121};{'S' * 81};Lyon;;03/11/2025;CDI\n"
    )
    client = client_for(company_a.admin)
    content = client.post(
        "/annuaire/import/", {"step": "upload", "file": upload(text)}
    ).content.decode()
    assert "Ligne 3 : « prenom » dépasse 60 caractères." in content
    assert "Ligne 3 : « poste » dépasse 120 caractères." in content
    assert "Ligne 3 : « service » dépasse 80 caractères." in content
    assert 'name="token"' not in content


def test_import_database_conflict_at_confirmation_is_not_a_server_error(
    client_for, company_a, monkeypatch
):
    from django.db import IntegrityError

    from apps.people import importer

    client = client_for(company_a.admin)
    text = HEADER + "Jean;Neuf;jean.neuf@exemple.fr;Comptable;Finance;Lyon;;03/11/2025;CDI\n"
    preview = client.post("/annuaire/import/", {"step": "upload", "file": upload(text)})
    token = preview.content.decode().split('name="token" value="')[1].split('"')[0]

    def conflict(*args, **kwargs):
        raise IntegrityError("doublon apparu entre l'aperçu et la confirmation")

    monkeypatch.setattr(importer, "run", conflict)
    done = client.post("/annuaire/import/", {"step": "confirm", "token": token})
    assert done.status_code == 302 and done["Location"] == "/annuaire/import/"
    page = client.get(done["Location"]).content.decode()
    assert "L&#x27;import n&#x27;a pas pu être enregistré. Recommencez." in page


def test_duplicate_email_reaching_the_service_is_a_message_not_a_500(
    client_for, company_a, monkeypatch
):
    """Deux créations simultanées passent toutes deux le contrôle du formulaire : la
    contrainte unique de la base tranche, et create_employee traduit l'IntegrityError."""
    from apps.people import views

    with tenant_context(company_a.company):
        with pytest.raises(services.PeopleError) as error:
            services.create_employee(
                {"first_name": "Léa", "last_name": "Double", "email": company_a.manager.email},
                context=ActionContext(company_a.hr),
            )
        assert error.value.field == "email"
        assert Employee.objects.filter(last_name="Double").count() == 0
    # Classe utilisée par la vue (un test d'isolation recharge apps.people.forms).
    monkeypatch.setattr(views.EmployeeForm, "clean_email", lambda form: form.cleaned_data["email"])
    response = client_for(company_a.hr).post(
        "/annuaire/nouveau/", form_data(company_a, email=company_a.manager.email.upper())
    )
    assert response.status_code == 422
    assert "Cette adresse est déjà utilisée par une autre fiche de l" in response.content.decode()
