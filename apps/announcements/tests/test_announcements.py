"""Communication interne (docs/modules/08-annonces.md) : critères d'acceptation, droits,
affichage sûr du texte, notifications, suppression annulable."""

import json

import pytest

from apps.announcements import services
from apps.announcements.models import Announcement, AnnouncementRead
from apps.core.context import ActionContext
from apps.core.models import AuditLog, Notification
from apps.core.tenancy import tenant_context
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

FORM = {
    "title": "Exercice d'évacuation",
    "category": "safety",
    "body": "Un exercice aura lieu jeudi à 10 h devant l'entrée principale.",
}


def detail_url(announcement):
    return f"/annonces/{announcement.public_id}/"


def trigger(response) -> dict:
    return json.loads(response["HX-Trigger"])


def location(response) -> str:
    return json.loads(response["HX-Location"])["path"]


def publish(company_data, **changes):
    with tenant_context(company_data.company):
        data = services.AnnouncementData(**{**FORM, **changes})
        return services.publish(data, context=ActionContext(company_data.hr))


# ---------- Lecture ----------


def test_opening_marks_as_read_for_this_person_only_and_updates_the_counter(client_for, company_a):
    announcement = company_a.requests["announcement"]
    employee, manager = client_for(company_a.employee), client_for(company_a.manager)
    assert "1 annonce non lue" in employee.get("/annonces/").content.decode()
    assert employee.get(detail_url(announcement)).status_code == 200
    assert "Vous avez tout lu" in employee.get("/annonces/").content.decode()
    assert "1 annonce non lue" in manager.get("/annonces/").content.decode()
    employee.get(detail_url(announcement))  # deuxième ouverture : toujours une lecture
    assert (
        AnnouncementRead.all_companies.filter(
            announcement=announcement, employee=company_a.employee
        ).count()
        == 1
    )


def test_pinned_first_then_by_date_with_search_and_category(client_for, company_a):
    publish(company_a, title="Annonce épinglée récente", pinned=True)
    publish(company_a, title="Annonce simple récente")
    page = client_for(company_a.employee).get("/annonces/").content.decode()
    content = page.split('id="results"', 1)[1]  # la cloche affiche aussi les titres
    assert content.index("Annonce épinglée récente") < content.index("Annonce simple récente")
    assert content.index("Annonce simple récente") < content.index("Fermeture du site")
    found = client_for(company_a.employee).get("/annonces/?q=fermé&categorie=site_life")
    results = found.content.decode().split('id="results"', 1)[1]
    assert "Fermeture du site" in results and "Annonce simple" not in results
    empty = client_for(company_a.employee).get("/annonces/?categorie=hr").content.decode()
    assert "Aucune annonce ne correspond à ces filtres." in empty


def test_script_is_shown_as_text_and_links_are_detected(client_for, company_a):
    announcement = publish(
        company_a,
        body="<script>alert('x')</script> Détails : https://exemple.fr/plan\njavascript:alert(1)",
    )
    content = client_for(company_a.employee).get(detail_url(announcement)).content.decode()
    assert "<script>alert" not in content
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in content
    assert '<a href="https://exemple.fr/plan" rel="nofollow">' in content
    assert 'href="javascript' not in content
    listing = client_for(company_a.employee).get("/annonces/").content.decode()
    assert "<script>alert" not in listing


# ---------- Droits ----------


@pytest.mark.parametrize("who", ["employee", "manager"])
def test_employee_and_manager_see_no_management_button_and_get_403(client_for, company_a, who):
    announcement = company_a.requests["announcement"]
    client = client_for(getattr(company_a, who))
    page = client.get(detail_url(announcement)).content.decode()
    for label in ("Modifier", "Supprimer", "Épingler", "Lectures"):
        assert f">{label}<" not in page and label not in page.split("<main", 1)[1]
    assert "Nouvelle annonce" not in client.get("/annonces/").content.decode()
    base = detail_url(announcement)
    for method, url in (
        ("get", "/annonces/nouvelle/"),
        ("post", "/annonces/nouvelle/"),
        ("get", f"{base}modifier/"),
        ("post", f"{base}epingler/"),
        ("get", f"{base}supprimer/"),
        ("post", f"{base}supprimer/"),
    ):
        assert getattr(client, method)(url).status_code == 403, url


def test_reads_are_shown_to_the_author_hr_and_admin_only(client_for, company_a):
    announcement = company_a.requests["announcement"]
    for who in ("hr", "admin"):
        page = client_for(getattr(company_a, who)).get(detail_url(announcement)).content.decode()
        assert "Lectures" in page
    # Seules les personnes présentes comptent (le départ et l'arrivée à venir ne comptent pas).
    EmployeeFactory(company=company_a.company, status="left")
    with tenant_context(company_a.company):
        from apps.announcements import selectors

        readers, total = selectors.read_stats(announcement)
        assert readers == 2  # l'auteur (RH) et l'administrateur, qui vient de l'ouvrir
        assert total == 5  # admin, RH, manager, salarié, invitée sans compte (actifs)
        assert services.can_see_reads(company_a.hr, announcement)
        assert not services.can_see_reads(company_a.manager, announcement)


# ---------- Publication, modification, épinglage ----------


def test_publishing_notifies_every_present_employee_and_emails_only_pinned(client_for, company_a):
    client = client_for(company_a.hr)
    response = client.post("/annonces/nouvelle/", FORM)
    assert response.status_code == 204
    assert trigger(response)["toast"]["title"] == "Annonce publiée"
    announcement = Announcement.all_companies.get(title=FORM["title"])
    assert location(response) == detail_url(announcement)
    sent = Notification.all_companies.filter(url=detail_url(announcement))
    assert set(sent.values_list("recipient_id", flat=True)) == {
        company_a.admin.pk,
        company_a.manager.pk,
        company_a.employee.pk,
        company_a.pending.pk,
    }
    assert not sent.exclude(email_subject="").exists()
    client.post("/annonces/nouvelle/", {**FORM, "title": "Important", "pinned": "on"})
    pinned = Announcement.all_companies.get(title="Important")
    emailed = Notification.all_companies.filter(url=detail_url(pinned)).exclude(email_subject="")
    assert emailed.count() == 4
    audit = AuditLog.all_companies.filter(action="announcements.published")
    assert audit.count() == 2 and not audit.filter(summary__contains="exercice aura lieu").exists()


def test_short_message_is_refused(client_for, company_a):
    response = client_for(company_a.hr).post("/annonces/nouvelle/", {**FORM, "body": "Trop court"})
    assert response.status_code == 422
    assert "Le message est trop court (15 caractères minimum)." in response.content.decode()
    with tenant_context(company_a.company), pytest.raises(services.AnnouncementError):
        services.publish(
            services.AnnouncementData(**{**FORM, "body": "court"}),
            context=ActionContext(company_a.hr),
        )


def test_editing_and_pinning_do_not_notify_again(client_for, company_a):
    announcement = company_a.requests["announcement"]
    client = client_for(company_a.hr)
    before = Notification.all_companies.count()
    edited = client.post(
        f"{detail_url(announcement)}modifier/",
        {**FORM, "title": "Titre corrigé"},
    )
    assert edited.status_code == 204
    assert client.post(f"{detail_url(announcement)}epingler/").status_code == 204
    announcement.refresh_from_db()
    assert announcement.title == "Titre corrigé" and announcement.pinned
    assert Notification.all_companies.count() == before
    unpin = client.post(f"{detail_url(announcement)}epingler/")
    assert trigger(unpin)["toast"]["title"] == "Annonce désépinglée"


# ---------- Suppression annulable ----------


def test_delete_asks_for_confirmation_then_can_be_undone_once(client_for, company_a):
    announcement = company_a.requests["announcement"]
    client = client_for(company_a.hr)
    confirm = client.get(f"{detail_url(announcement)}supprimer/").content.decode()
    assert "Supprimer cette annonce ?" in confirm
    response = client.post(f"{detail_url(announcement)}supprimer/")
    assert location(response) == "/annonces/"
    gone = client_for(company_a.employee).get(detail_url(announcement))
    assert gone.status_code == 404
    assert "Cette annonce a été supprimée." in gone.content.decode()
    assert "Fermeture du site" not in client.get("/annonces/").content.decode()
    undo_url = trigger(response)["toast"]["undo_url"]
    assert client_for(company_a.admin).post(undo_url).status_code == 409  # pas l'auteur
    undone = client.post(undo_url)
    assert trigger(undone)["toast"]["title"] == "Suppression annulée"
    assert client_for(company_a.employee).get(detail_url(announcement)).status_code == 200
    assert client.post(undo_url).status_code == 409  # jeton rejoué


def test_undo_token_of_another_company_is_refused(client_for, company_a, company_b):
    announcement = company_a.requests["announcement"]
    response = client_for(company_a.hr).post(f"{detail_url(announcement)}supprimer/")
    undo_url = trigger(response)["toast"]["undo_url"]
    assert client_for(company_b.hr).post(undo_url).status_code == 409
    assert Announcement.all_companies.get(pk=announcement.pk).deleted_at is not None


def test_disabled_module_shows_the_dedicated_page(client_for, company_a):
    from apps.core.models import CompanyModule

    CompanyModule.all_companies.filter(company=company_a.company, module="announcements").update(
        enabled=False
    )
    page = client_for(company_a.employee).get("/annonces/").content.decode()
    assert "Module désactivé" in page


# ---------- Annonce épinglée supprimée (L6-18) ----------


def test_pinned_announcement_deleted_within_45_seconds_sends_no_email(
    client_for, company_a, run_tasks
):
    from django.core import mail

    client = client_for(company_a.hr)
    client.post("/annonces/nouvelle/", {**FORM, "pinned": "on"})
    announcement = Announcement.all_companies.get(title=FORM["title"])
    client.post(f"{detail_url(announcement)}supprimer/")
    assert not Notification.all_companies.filter(url=detail_url(announcement)).exists()
    run_tasks(after_seconds=46)
    assert mail.outbox == []


def test_undoing_a_deletion_recreates_notifications_without_resending_emails(
    client_for, company_a, run_tasks
):
    from django.core import mail

    client = client_for(company_a.hr)
    client.post("/annonces/nouvelle/", {**FORM, "pinned": "on"})
    announcement = Announcement.all_companies.get(title=FORM["title"])
    run_tasks(after_seconds=46)
    sent = len(mail.outbox)
    assert sent == 3  # admin, manager, salarié ; l'invitée n'a pas encore de compte
    # Une notification sans e-mail parti (arrivée après la publication) : retirée puis
    # recréée ; les e-mails déjà partis ne sont jamais renvoyés.
    late = EmployeeFactory(company=company_a.company, last_name="Arrivee")
    response = client.post(f"{detail_url(announcement)}supprimer/")
    kept = Notification.all_companies.filter(url=detail_url(announcement))
    # Restent les 3 notifications dont l'e-mail est parti ; celle de l'invitée sans compte
    # (aucun e-mail) est retirée, comme celle de la personne arrivée ensuite (aucune).
    assert kept.count() == 3 and not kept.filter(email_sent_at__isnull=True).exists()
    client.post(trigger(response)["toast"]["undo_url"])
    recreated = Notification.all_companies.filter(url=detail_url(announcement))
    assert recreated.count() == 5 and recreated.filter(recipient=late).exists()
    run_tasks(after_seconds=46)
    assert len(mail.outbox) == sent + 1
    assert mail.outbox[-1].to == [late.user.email]


def test_email_task_skips_a_notification_whose_announcement_is_gone(company_a, run_tasks):
    """La tâche vérifie aussi l'objet source, même si la notification est restée."""
    from django.core import mail

    with tenant_context(company_a.company):
        announcement = services.publish(
            services.AnnouncementData(**FORM, pinned=True), context=ActionContext(company_a.hr)
        )
    Announcement.all_companies.filter(pk=announcement.pk).update(
        deleted_at=announcement.published_at
    )
    run_tasks(after_seconds=46)
    assert mail.outbox == []
