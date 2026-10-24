"""Tâches en arrière-plan (T-11, L3-01) : moteur base de données de django.tasks.

Règle (A3-04) : une ligne de tâche ne contient jamais de donnée sensible en clair.
- Les e-mails de Dianna reçoivent des identifiants (notification, invitation, fiche) ;
  le contenu est construit au moment de l'envoi. Le jeton d'invitation est créé ici et
  n'existe en clair que dans l'e-mail ; seule son empreinte est enregistrée.
- Les e-mails d'allauth, déjà rendus, sont passés chiffrés (TASKS_ENCRYPTION_KEY).
- Le résultat d'une tâche réussie est supprimé dès la fin de la tâche (signal ci-dessous) ;
  les échecs sont purgés après 7 jours (`manage.py purge_task_results`, planifié).
"""

import json
import logging

from django.core.mail import EmailMultiAlternatives
from django.tasks import task
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def _send(subject, body, to, from_email=None, html=""):
    message = EmailMultiAlternatives(subject, body, from_email, to)
    if html:
        message.attach_alternative(html, "text/html")
    message.send()


def _company(company_id):
    from apps.core.models import Company

    return Company.objects.filter(pk=company_id, status=Company.Status.ACTIVE).first()


@task
def send_notification_email(company_id: int, notification_id: int) -> str:
    """E-mail d'une notification. Si la notification n'existe plus (action annulée, demande
    traitée entre-temps) ou si son objet source a disparu, rien ne part (L0-03, A3-05)."""
    from apps.core import notifications
    from apps.core.hosts import company_url
    from apps.core.models import Notification
    from apps.core.tenancy import tenant_context

    company = _company(company_id)
    if company is None:
        return "skipped"
    with tenant_context(company):
        notification = (
            Notification.objects.select_related("recipient", "recipient__user")
            .filter(pk=notification_id)
            .first()
        )
        if notification is None or notification.email_sent_at is not None:
            return "skipped"
        if not notifications.source_is_current(notification):
            return "skipped"  # objet supprimé ou retiré entre-temps (L6-18)
        user = notification.recipient.user
        if user is None or not user.is_active or not notification.email_subject:
            return "skipped"
        body = render_to_string(
            "core/email/notification.txt",
            {
                "recipient": notification.recipient,
                "text": notification.text,
                "url": company_url(company, notification.url or "/"),
            },
        )
        _send(notification.email_subject, body, [user.email])
        notification.email_sent_at = timezone.now()
        notification.save(update_fields=["email_sent_at", "updated_at"])
    return "sent"


@task
def send_invitation_email(company_id: int, invitation_id: int) -> str:
    """Crée le jeton d'invitation et l'envoie. Son empreinte n'est enregistrée qu'une fois
    l'e-mail accepté par le serveur d'envoi ; sinon l'invitation est marquée « Envoi
    échoué », la précédente reste valable, et la tâche échoue (purgée après 7 jours)."""
    import secrets

    from apps.accounts import services as accounts
    from apps.accounts.models import Invitation
    from apps.core.tenancy import tenant_context

    company = _company(company_id)
    if company is None:
        return "skipped"
    with tenant_context(company):
        invitation = Invitation.objects.select_related("employee").filter(pk=invitation_id).first()
        if invitation is None or not invitation.is_usable or invitation.sent_at is not None:
            return "skipped"
        token = secrets.token_urlsafe(32)
        context = {
            "employee": invitation.employee,
            "company": company,
            "url": accounts.invitation_url(invitation, token),
            "days": Invitation.VALIDITY_DAYS,
        }
        subject = render_to_string("accounts/email/invitation_subject.txt", context).strip()
        body = render_to_string("accounts/email/invitation_message.txt", context)
        # Un échec de l'envoi ou de sa confirmation laisse le lien inutilisable : « Envoi
        # échoué », l'invitation précédente reste valable.
        try:
            _send(subject, body, [invitation.employee.email])
            accounts.confirm_sent(invitation, token)
        except Exception:
            accounts.mark_send_failed(invitation)
            raise
    return "sent"


@task
def send_space_link_email(company_id: int, employee_id: int) -> str:
    """Lien de la vitrine vers l'espace de l'entreprise (L1-12)."""
    from apps.core.hosts import company_url
    from apps.core.tenancy import tenant_context
    from apps.people.models import Employee

    company = _company(company_id)
    if company is None:
        return "skipped"
    with tenant_context(company):
        employee = Employee.objects.select_related("user").filter(pk=employee_id).first()
        if employee is None or not employee.can_sign_in:
            return "skipped"
        context = {
            "employee": employee,
            "company": company,
            "url": company_url(company, "/connexion/"),
        }
        subject = render_to_string("public/email/space_link_subject.txt", context).strip()
        body = render_to_string("public/email/space_link_message.txt", context)
        _send(subject, body, [employee.user.email])
    return "sent"


@task
def send_encrypted_email(payload: str) -> str:
    """E-mail déjà rendu (allauth), passé chiffré avec TASKS_ENCRYPTION_KEY."""
    from apps.core import crypto

    data = json.loads(crypto.decrypt("TASKS_ENCRYPTION_KEY", payload))
    _send(data["subject"], data["body"], data["to"], data.get("from_email"), data.get("html", ""))
    return "sent"


def delete_successful_result(sender, task_result, **kwargs):
    """Signal task_finished : le résultat d'une tâche réussie est supprimé tout de suite."""
    from django.tasks import TaskResultStatus
    from django_tasks_db.models import DBTaskResult

    if task_result.status != TaskResultStatus.SUCCESSFUL:
        return
    try:
        DBTaskResult.objects.filter(id=task_result.id).delete()
    except Exception:  # la tâche a réussi : la purge planifiée rattrapera.
        logger.warning("Résultat de tâche non supprimé id=%s", task_result.id)
