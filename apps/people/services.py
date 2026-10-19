"""Annuaire : création, modification, archivage, profils (docs/modules/03-annuaire.md).

Chaque transition vérifie l'état de départ, écrit l'historique de la fiche (EmployeeChange,
noms des champs seulement) et le journal d'audit (sans contenu personnel)."""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import audit
from apps.people.models import Employee, EmployeeChange, EmployeeStatus, Role

# Champs suivis dans l'historique ; « photo » est enregistrée à part (fichier).
TRACKED_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "phone",
    "office",
    "job_title",
    "service",
    "site",
    "manager",
    "arrival_date",
    "departure_date",
    "contract_type",
    "work_time",
    "registration_number",
    "role",
    "status",
)


class PeopleError(Exception):
    def __init__(self, message):
        super().__init__(str(message))
        self.message = message


def _record(employee, actor, kind, fields=(), *, request=None, action=None, summary=None):
    EmployeeChange.objects.create(
        employee=employee, actor=actor, kind=kind, fields=sorted(set(fields))
    )
    audit.log(
        action or f"people.{kind}",
        summary or f"{EmployeeChange.Kind(kind).label} : {employee.full_name}",
        actor=actor,
        target=employee,
        request=request,
    )


def status_for_arrival(arrival_date) -> str:
    """Date d'arrivée future : « Arrivée prochaine »."""
    if arrival_date and arrival_date > timezone.localdate():
        return EmployeeStatus.UPCOMING
    return EmployeeStatus.ACTIVE


def active_admins(exclude=None):
    admins = Employee.objects.filter(
        role=Role.ADMIN, status__in=(EmployeeStatus.ACTIVE, EmployeeStatus.UPCOMING)
    )
    if exclude is not None:
        admins = admins.exclude(pk=exclude.pk)
    return admins


def ensure_an_admin_remains(employee, *, new_role=None, leaving=False):
    """Il doit toujours rester au moins un administrateur actif (fiche administration)."""
    losing_admin = employee.role == Role.ADMIN and (
        leaving or (new_role and new_role != Role.ADMIN)
    )
    if losing_admin and not active_admins(exclude=employee).exists():
        raise PeopleError(
            _(
                "%(name)s est le dernier administrateur actif. Donnez d'abord le profil "
                "Administrateur à une autre personne."
            )
            % {"name": employee.full_name}
        )


@transaction.atomic
def create_employee(data: dict, *, actor, photo=None, request=None) -> Employee:
    """Crée la fiche au profil Salarié ; un autre profil est ensuite attribué par change_role
    (journalisé people.role_changed, comme tout changement de profil)."""
    data = dict(data)
    role = data.pop("role", None) or Role.EMPLOYEE
    employee = Employee(**data)
    employee.status = status_for_arrival(employee.arrival_date)
    if photo is not None:
        employee.photo.save(photo.name, photo, save=False)
    employee.save()
    _record(employee, actor, EmployeeChange.Kind.CREATED, request=request)
    if role != Role.EMPLOYEE:
        change_role(employee, role, actor=actor, request=request)
        employee.refresh_from_db()
    return employee


@transaction.atomic
def update_employee(
    employee: Employee, data: dict, *, actor, photo=None, remove_photo=False, request=None
) -> list[str]:
    """Applique les changements et renvoie la liste des champs modifiés. Le profil d'accès
    passe par change_role (refus sur sa propre fiche, dernier administrateur protégé,
    journal people.role_changed)."""
    data = dict(data)
    role = data.pop("role", None)
    role_changed = role is not None and role != Employee.objects.get(pk=employee.pk).role
    if role_changed:
        change_role(employee, role, actor=actor, request=request)
    employee = Employee.objects.select_for_update().get(pk=employee.pk)
    changed = []
    for name, value in data.items():
        current = getattr(employee, name)
        if current != value:
            setattr(employee, name, value)
            changed.append(name)
    if "arrival_date" in changed and employee.status != EmployeeStatus.LEFT:
        new_status = status_for_arrival(employee.arrival_date)
        if new_status != employee.status:
            employee.status = new_status
            changed.append("status")
    if photo is not None:
        if employee.photo:
            employee.photo.delete(save=False)
        employee.photo.save(photo.name, photo, save=False)
        changed.append("photo")
    elif remove_photo and employee.photo:
        employee.photo.delete(save=False)
        changed.append("photo")
    if changed:
        employee.save()
        _record(employee, actor, EmployeeChange.Kind.UPDATED, changed, request=request)
    return ["role", *changed] if role_changed else changed


@transaction.atomic
def update_contact(employee: Employee, *, phone: str, office: str, request=None) -> list[str]:
    """Le salarié modifie son téléphone et son bureau (modale « Modifier mes coordonnées »)."""
    employee = Employee.objects.select_for_update().get(pk=employee.pk)
    changed = []
    for name, value in (("phone", phone), ("office", office)):
        if getattr(employee, name) != value:
            setattr(employee, name, value)
            changed.append(name)
    if changed:
        employee.save(update_fields=[*changed, "updated_at"])
        _record(employee, employee, EmployeeChange.Kind.CONTACT, changed, request=request)
    return changed


@transaction.atomic
def archive(employee: Employee, *, actor, departure_date=None, request=None) -> dict:
    """Statut « Parti », date de départ (aujourd'hui par défaut), compte désactivé, données
    conservées. Renvoie l'état précédent, pour l'annulation immédiate."""
    employee = Employee.objects.select_for_update().get(pk=employee.pk)
    if employee.status == EmployeeStatus.LEFT:
        raise PeopleError(_("Cette fiche est déjà archivée."))
    if actor is not None and actor.pk == employee.pk:
        raise PeopleError(_("Vous ne pouvez pas archiver votre propre fiche."))
    ensure_an_admin_remains(employee, leaving=True)
    previous = {
        "status": employee.status,
        "departure_date": employee.departure_date.isoformat() if employee.departure_date else "",
    }
    employee.status = EmployeeStatus.LEFT
    employee.departure_date = departure_date or timezone.localdate()
    employee.save(update_fields=["status", "departure_date", "updated_at"])
    if employee.user_id:
        employee.user.is_active = False
        employee.user.save(update_fields=["is_active", "updated_at"])
    _record(
        employee,
        actor,
        EmployeeChange.Kind.ARCHIVED,
        ["status", "departure_date"],
        request=request,
    )
    return previous


@transaction.atomic
def undo_archive(employee: Employee, previous: dict, *, actor, request=None) -> None:
    from datetime import date

    employee = Employee.objects.select_for_update().get(pk=employee.pk)
    if employee.status != EmployeeStatus.LEFT:
        return
    employee.status = previous["status"]
    employee.departure_date = (
        date.fromisoformat(previous["departure_date"]) if previous["departure_date"] else None
    )
    employee.save(update_fields=["status", "departure_date", "updated_at"])
    if employee.user_id:
        employee.user.is_active = True
        employee.user.save(update_fields=["is_active", "updated_at"])
    _record(
        employee,
        actor,
        EmployeeChange.Kind.REACTIVATED,
        ["status", "departure_date"],
        request=request,
        summary=_("Archivage annulé : %(name)s") % {"name": employee.full_name},
    )


@transaction.atomic
def reactivate(employee: Employee, *, actor, request=None) -> None:
    employee = Employee.objects.select_for_update().get(pk=employee.pk)
    if employee.status != EmployeeStatus.LEFT:
        raise PeopleError(_("Cette fiche n'est pas archivée."))
    employee.status = EmployeeStatus.ACTIVE
    employee.departure_date = None
    employee.save(update_fields=["status", "departure_date", "updated_at"])
    if employee.user_id:
        employee.user.is_active = True
        employee.user.save(update_fields=["is_active", "updated_at"])
    _record(
        employee,
        actor,
        EmployeeChange.Kind.REACTIVATED,
        ["status", "departure_date"],
        request=request,
    )


@transaction.atomic
def change_role(employee: Employee, role: str, *, actor, request=None) -> None:
    """Profil d'accès (Administrateur seulement). Effet à la requête suivante de la personne ;
    un passage à RH ou Admin impose la double authentification (T-10)."""
    employee = Employee.objects.select_for_update().get(pk=employee.pk)
    if role not in Role.values:
        raise PeopleError(_("Profil inconnu."))
    if actor is not None and actor.pk == employee.pk:
        raise PeopleError(_("Vous ne pouvez pas modifier votre propre profil."))
    if employee.role == role:
        return
    ensure_an_admin_remains(employee, new_role=role)
    old = employee.get_role_display()
    employee.role = role
    employee.save(update_fields=["role", "updated_at"])
    _record(
        employee,
        actor,
        EmployeeChange.Kind.ROLE,
        ["role"],
        request=request,
        action="people.role_changed",
        summary=_("Profil de %(name)s : %(old)s → %(new)s")
        % {"name": employee.full_name, "old": old, "new": employee.get_role_display()},
    )


def would_loop(employee: Employee, manager: Employee | None) -> bool:
    """Le choix de ce manager créerait-il une boucle dans la hiérarchie ?"""
    seen = set()
    current = manager
    while current is not None:
        if employee.pk is not None and current.pk == employee.pk:
            return True
        if current.pk in seen:
            return True
        seen.add(current.pk)
        current = current.manager
    return False
