import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import Invitation, User
from apps.core.models import AuditLog, Notification
from apps.core.tenancy import tenant_context
from apps.people.models import Employee
from tests.factories import EmployeeFactory, UserFactory

pytestmark = pytest.mark.django_db
STRONG = "Une-phrase-de-passe-solide-2026"


def test_invitation_mail_points_to_the_company_space(company_a, run_tasks):
    with tenant_context(company_a.company):
        newcomer = EmployeeFactory(company=company_a.company, user=None)
        invitation = services.invite(newcomer, sent_by=company_a.admin)
        placeholder = invitation.token_hash
    assert mail.outbox == []  # envoyée par le travailleur de tâches (L1-14)
    run_tasks()
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [newcomer.email]
    token = re.search(r"http://exemple\.localhost/invitation/([\w-]+)/", message.body).group(1)
    # Jeton créé par la tâche : seule son empreinte est stockée (A3-04).
    invitation = Invitation.all_companies.get(pk=invitation.pk)
    assert invitation.token_hash == services.hash_token(token) != placeholder
    with tenant_context(company_a.company):
        assert AuditLog.objects.filter(action="account.invitation_sent").exists()


def test_new_invitation_replaces_the_previous_one_once_sent(company_a, run_tasks):
    with tenant_context(company_a.company):
        services.invite(company_a.pending)
        assert Invitation.objects.get(pk=company_a.invitation.pk).is_usable  # pas encore partie
    run_tasks()
    with tenant_context(company_a.company):
        first = Invitation.objects.get(pk=company_a.invitation.pk)
    assert first.revoked_at is not None and not first.is_usable


def test_inviting_an_address_used_in_another_company_is_refused(company_a, company_b):
    with tenant_context(company_a.company):
        newcomer = EmployeeFactory(
            company=company_a.company, user=None, email=company_b.employee.email
        )
        with pytest.raises(services.InvitationError) as error:
            services.invite(newcomer)
    assert str(error.value.message) == (
        "Cette adresse est déjà utilisée sur Dianna. Utilisez une autre adresse ou contactez le "
        "support."
    )


def test_invitation_page_and_password_rules(anonymous_client, company_a):
    client = anonymous_client(company_a.company)
    url = f"/invitation/{company_a.invitation_token}/"
    page = client.get(url)
    assert page.status_code == 200
    assert company_a.pending.email in page.content.decode()
    response = client.post(url, {"password1": "court", "password2": "court"})
    assert response.status_code == 422
    assert "12 caractères" in response.content.decode()
    response = client.post(url, {"password1": STRONG, "password2": STRONG + "x"})
    assert "Les deux mots de passe ne correspondent pas." in response.content.decode()


def test_accepting_creates_the_account_with_the_email_of_the_record(anonymous_client, company_a):
    client = anonymous_client(company_a.company)
    url = f"/invitation/{company_a.invitation_token}/"
    response = client.post(url, {"password1": STRONG, "password2": STRONG})
    assert response.status_code == 302 and response["Location"] == "/"
    employee = Employee.all_companies.get(pk=company_a.pending.pk)
    assert employee.user.email == company_a.pending.email.lower()
    assert employee.user.check_password(STRONG)
    assert client.get("/").status_code == 200
    # Le lien ne sert qu'une fois.
    assert client.get(url).status_code == 410


def test_changing_the_record_email_does_not_change_the_login(company_a):
    with tenant_context(company_a.company):
        employee = Employee.objects.get(pk=company_a.employee.pk)
        employee.email = "camille.nouvelle@exemple.fr"
        employee.save()
    assert User.objects.get(pk=company_a.employee.user_id).email != "camille.nouvelle@exemple.fr"


def test_expired_link_offers_a_new_invitation_once(anonymous_client, company_a):
    Invitation.all_companies.filter(pk=company_a.invitation.pk).update(
        expires_at=timezone.now() - timedelta(days=1)
    )
    client = anonymous_client(company_a.company)
    url = f"/invitation/{company_a.invitation_token}/"
    page = client.get(url)
    assert page.status_code == 410
    assert "Demander une nouvelle invitation" in page.content.decode()
    assert client.post(url, {"password1": STRONG, "password2": STRONG}).status_code == 410
    confirm = client.post(f"{url}renouveler/")
    assert "Demande transmise." in confirm.content.decode()
    client.post(f"{url}renouveler/")
    with tenant_context(company_a.company):
        notes = Notification.objects.filter(recipient=company_a.admin)
        assert notes.filter(text__contains="nouvelle invitation").count() == 1


def test_accept_refuses_when_the_address_was_taken_meanwhile(company_a):
    UserFactory(email=company_a.pending.email)
    with tenant_context(company_a.company), pytest.raises(services.InvitationError):
        services.accept(company_a.invitation, STRONG)


def test_theme_is_saved_on_the_account(client_for, company_a):
    client = client_for(company_a.employee)
    assert client.post("/compte/theme/", {"theme": "dark"}).status_code == 204
    assert User.objects.get(pk=company_a.employee.user_id).theme == "dark"
    assert client.post("/compte/theme/", {"theme": "rose"}).status_code == 400
    assert 'data-user-theme="dark"' in client.get("/").content.decode()


def test_failed_send_keeps_the_previous_invitation(company_a, client_for, run_tasks, monkeypatch):
    """L'empreinte n'est enregistrée qu'après l'acceptation de l'e-mail par le serveur
    d'envoi ; un échec laisse l'invitation précédente valable et affiche « Envoi échoué »."""
    from smtplib import SMTPException

    from django.tasks import TaskResultStatus
    from django_tasks_db.models import DBTaskResult

    from apps.core import tasks

    previous_token = company_a.invitation_token

    def refuse(*args, **kwargs):
        raise SMTPException("550 boîte inconnue")

    with tenant_context(company_a.company):
        new = services.invite(company_a.pending, sent_by=company_a.admin)
        placeholder = new.token_hash
    monkeypatch.setattr(tasks, "_send", refuse)
    run_tasks()
    monkeypatch.undo()

    assert mail.outbox == []
    assert DBTaskResult.objects.get().status == TaskResultStatus.FAILED
    with tenant_context(company_a.company):
        new = Invitation.objects.get(pk=new.pk)
        assert new.send_failed and new.token_hash == placeholder
        still_valid = services.find_invitation(previous_token)
        assert still_valid.pk == company_a.invitation.pk and still_valid.is_usable
    page = client_for(company_a.admin).get("/administration/utilisateurs/").content.decode()
    assert "Envoi échoué" in page and "Renvoyer l'invitation" in page

    # « Renvoyer » : l'envoi réussit, l'ancienne invitation est remplacée.
    with tenant_context(company_a.company):
        retry = services.invite(company_a.pending, sent_by=company_a.admin)
    run_tasks()
    assert len(mail.outbox) == 1
    with tenant_context(company_a.company):
        assert not services.find_invitation(previous_token).is_usable
        retry = Invitation.objects.get(pk=retry.pk)
        assert retry.sent_at is not None and not retry.send_failed
    page = client_for(company_a.admin).get("/administration/utilisateurs/").content.decode()
    assert "Envoi échoué" not in page


def test_failed_confirmation_marks_the_send_as_failed(
    company_a, client_for, run_tasks, monkeypatch
):
    """L'e-mail est parti mais sa confirmation échoue : l'empreinte n'est pas enregistrée,
    le lien est inutilisable, donc « Envoi échoué » ; l'invitation précédente reste valable."""

    def broken(*args, **kwargs):
        raise RuntimeError("base indisponible")

    with tenant_context(company_a.company):
        new = services.invite(company_a.pending, sent_by=company_a.admin)
    monkeypatch.setattr(services, "confirm_sent", broken)
    run_tasks()
    monkeypatch.undo()
    assert len(mail.outbox) == 1
    with tenant_context(company_a.company):
        assert Invitation.objects.get(pk=new.pk).send_failed
        assert services.find_invitation(company_a.invitation_token).is_usable
    page = client_for(company_a.admin).get("/administration/utilisateurs/").content.decode()
    assert "Envoi échoué" in page


def test_confirmation_of_a_replaced_invitation_replaces_nothing(company_a, client_for):
    """Deux invitations envoyées l'une après l'autre ; la plus récente part la première.
    La confirmation tardive de l'ancienne ne remplace pas la nouvelle."""
    with tenant_context(company_a.company):
        older = services.invite(company_a.pending, sent_by=company_a.admin)
        newer = services.invite(company_a.pending, sent_by=company_a.admin)
        assert services.confirm_sent(newer, "jeton-recent") is True
        assert services.confirm_sent(older, "jeton-ancien") is False
        newer = Invitation.objects.get(pk=newer.pk)
        older = Invitation.objects.get(pk=older.pk)
        assert newer.is_usable and newer.revoked_at is None
        assert older.revoked_at is not None and not older.is_usable
        assert services.find_invitation("jeton-recent").pk == newer.pk
        assert not services.find_invitation("jeton-ancien").is_usable
        latest = services.latest_open_invitations([company_a.pending])
        assert latest[company_a.pending.pk].pk == newer.pk
    page = client_for(company_a.admin).get("/administration/utilisateurs/").content.decode()
    assert "Invitation envoyée" in page and "Envoi échoué" not in page


def test_confirmation_never_replaces_a_newer_invitation_still_queued(company_a):
    with tenant_context(company_a.company):
        older = services.invite(company_a.pending, sent_by=company_a.admin)
        newer = services.invite(company_a.pending, sent_by=company_a.admin)
        assert services.confirm_sent(older, "jeton-ancien") is True
        assert Invitation.objects.get(pk=newer.pk).is_usable  # partira à son tour
        assert not Invitation.objects.get(pk=company_a.invitation.pk).is_usable
