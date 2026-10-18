"""Comptes : invitations et changements liés à la connexion (T-09).

Chaque transition vérifie l'état de départ, écrit le journal d'audit et, le cas échéant,
crée la notification (conventions de CLAUDE.md)."""

import hashlib
import secrets
from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.models import Invitation, User, normalize_email
from apps.core import audit, notifications
from apps.core.hosts import company_url
from apps.people.models import Employee, EmployeeStatus, Role

EMAIL_TAKEN = _(
    "Cette adresse est déjà utilisée sur Dianna. "
    "Utilisez une autre adresse ou contactez le support."
)


class InvitationError(Exception):
    def __init__(self, message):
        super().__init__(str(message))
        self.message = message


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def email_is_taken(email: str, *, except_user=None) -> bool:
    """Un compte Dianna utilise déjà cette adresse comme identifiant (toutes entreprises)."""
    users = User.objects.filter(email=normalize_email(email))
    if except_user is not None:
        users = users.exclude(pk=except_user.pk)
    return users.exists()


def invitation_url(invitation, token: str) -> str:
    # Routes de l'espace client, même quand l'invitation part de l'hôte éditeur.
    path = reverse("accounts:invitation", args=[token], urlconf="config.urls")
    return company_url(invitation.employee.company, path)


@transaction.atomic
def invite(employee: Employee, *, sent_by: Employee | None = None, request=None):
    """Envoie (ou renvoie) une invitation. Renvoie (invitation, jeton en clair)."""
    if employee.user_id is not None:
        raise InvitationError(_("Cette personne a déjà un compte."))
    if employee.status == EmployeeStatus.LEFT:
        raise InvitationError(_("Impossible d'inviter une personne partie."))
    if email_is_taken(employee.email):
        raise InvitationError(EMAIL_TAKEN)

    now = timezone.now()
    Invitation.objects.filter(
        employee=employee, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now, updated_at=now)
    token = secrets.token_urlsafe(32)
    invitation = Invitation.objects.create(
        employee=employee,
        token_hash=hash_token(token),
        expires_at=now + timedelta(days=Invitation.VALIDITY_DAYS),
        sent_by=sent_by,
    )
    context = {
        "employee": employee,
        "company": employee.company,
        "url": invitation_url(invitation, token),
        "days": Invitation.VALIDITY_DAYS,
    }
    subject = render_to_string("accounts/email/invitation_subject.txt", context).strip()
    body = render_to_string("accounts/email/invitation_message.txt", context)
    transaction.on_commit(
        lambda: send_mail(subject, body, None, [employee.email], fail_silently=False)
    )
    audit.log(
        "account.invitation_sent",
        _("Invitation envoyée à %(name)s") % {"name": employee.full_name},
        actor=sent_by,
        target=employee,
        request=request,
    )
    return invitation, token


def find_invitation(token: str):
    """Invitation de l'entreprise courante pour ce jeton, utilisable ou non (None si absente)."""
    return (
        Invitation.objects.select_related("employee").filter(token_hash=hash_token(token)).first()
    )


@transaction.atomic
def accept(invitation: Invitation, password: str, *, request=None) -> User:
    invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
    employee = Employee.objects.select_for_update().get(pk=invitation.employee_id)
    invitation.employee = employee
    if not invitation.is_usable:
        raise InvitationError(_("Ce lien d'invitation n'est plus valable."))
    if email_is_taken(employee.email):
        raise InvitationError(EMAIL_TAKEN)
    user = User.objects.create_user(employee.email, password)
    employee.user = user
    employee.save(update_fields=["user", "updated_at"])
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at", "updated_at"])
    audit.log(
        "account.invitation_accepted",
        _("Compte créé par %(name)s") % {"name": employee.full_name},
        actor=employee,
        target=employee,
        request=request,
    )
    return user


@transaction.atomic
def request_renewal(invitation: Invitation, *, request=None) -> bool:
    """Lien expiré : prévient les administrateurs (une seule fois par invitation)."""
    invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
    if invitation.renewal_requested_at is not None or invitation.employee.user_id:
        return False
    invitation.renewal_requested_at = timezone.now()
    invitation.save(update_fields=["renewal_requested_at", "updated_at"])
    employee = invitation.employee
    admins = Employee.objects.filter(role=Role.ADMIN, user__is_active=True).exclude(
        status=EmployeeStatus.LEFT
    )
    for admin in admins:
        notifications.notify(
            admin,
            _("%(name)s demande une nouvelle invitation.") % {"name": employee.full_name},
            kind="account",
        )
    audit.log(
        "account.invitation_renewal_requested",
        _("Nouvelle invitation demandée par %(name)s") % {"name": employee.full_name},
        target=employee,
        request=request,
    )
    return True
