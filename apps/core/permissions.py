"""Permissions côté serveur (règle 2 de CLAUDE.md). La matrice docs/04-permissions.md fait foi.

Chaque action a une portée par colonne : Salarié, Manager, RH, Administrateur.
- La colonne « Manager » s'applique à toute personne qui a des collaborateurs directs, quel
  que soit son profil (L1-02). Les RH et administrateurs utilisent leur propre colonne.
- Portées : ALL (toute l'entreprise), TEAM (soi et ses collaborateurs directs), SELF (soi),
  SERVICE (son service ; pour un manager, plus son équipe d'autres services, L1-06), NONE.
- Personne ne décide pour soi-même (SELF_FORBIDDEN).
Les fonctions sont pures (pas d'accès à la requête) et testées unitairement.
"""

from django.db.models import Q, QuerySet

ALL, TEAM, SELF, SERVICE, NONE = "all", "team", "self", "service", None

EMPLOYEE_COL, MANAGER_COL, HR_COL, ADMIN_COL = 0, 1, 2, 3

#                                    Salarié  Manager  RH       Admin
RULES: dict[str, tuple] = {
    # Annuaire
    "people.view_list":                 (ALL,     ALL,     ALL,     ALL),
    "people.view_left":                 (NONE,    NONE,    ALL,     ALL),
    "people.view_hr":                   (SELF,    SELF,    ALL,     ALL),
    "people.edit_contact":              (SELF,    SELF,    ALL,     ALL),
    "people.manage":                    (NONE,    NONE,    ALL,     ALL),
    "people.assign_role":               (NONE,    NONE,    NONE,    ALL),
    "people.import":                    (NONE,    NONE,    NONE,    ALL),
    # Demandes : télétravail, congés, astreintes
    "requests.create":                  (SELF,    SELF,    SELF,    SELF),
    "requests.view":                    (SELF,    TEAM,    ALL,     ALL),
    "requests.decide":                  (NONE,    TEAM,    ALL,     ALL),
    "requests.manage_campaigns":        (NONE,    NONE,    ALL,     ALL),
    "requests.final_decision":          (NONE,    NONE,    ALL,     ALL),
    "requests.export":                  (NONE,    NONE,    ALL,     ALL),
    # Transport et matériel
    "transport.submit":                 (SELF,    SELF,    SELF,    SELF),
    "transport.view":                   (SELF,    SELF,    ALL,     ALL),
    "transport.decide":                 (NONE,    NONE,    ALL,     ALL),
    "equipment.request":                (SELF,    SELF,    SELF,    SELF),
    "equipment.view":                   (SELF,    TEAM,    ALL,     ALL),
    "equipment.decide":                 (NONE,    NONE,    ALL,     ALL),
    "equipment.manage":                 (NONE,    NONE,    ALL,     ALL),
    # Planning
    "planning.view":                    (SERVICE, SERVICE, ALL,     ALL),
    "planning.export":                  (SERVICE, SERVICE, ALL,     ALL),
    # Carrière et évaluations
    "careers.view":                     (SELF,    TEAM,    ALL,     ALL),
    "careers.launch":                   (NONE,    TEAM,    ALL,     ALL),
    "careers.self_assess":              (SELF,    SELF,    SELF,    SELF),
    "careers.evaluate":                 (NONE,    TEAM,    ALL,     ALL),
    "careers.sign":                     (SELF,    TEAM,    ALL,     ALL),
    "careers.add_note":                 (SELF,    TEAM,    ALL,     ALL),
    # Questionnaires
    "surveys.answer":                   (SELF,    SELF,    SELF,    SELF),
    "surveys.view_results":             (NONE,    ALL,     ALL,     ALL),
    "surveys.manage":                   (NONE,    NONE,    ALL,     ALL),
    # Communication interne
    "announcements.read":               (ALL,     ALL,     ALL,     ALL),
    "announcements.manage":             (NONE,    NONE,    ALL,     ALL),
    # Suivi d'intervention
    "interventions.write":              (SELF,    SELF,    SELF,    SELF),
    "interventions.view":               (SELF,    TEAM,    ALL,     ALL),
    "interventions.decide":             (NONE,    TEAM,    ALL,     ALL),
    # Administration
    "admin.manage":                     (NONE,    NONE,    NONE,    ALL),
}  # fmt: skip

# Personne ne valide sa propre demande ni n'évalue son propre entretien.
SELF_FORBIDDEN = frozenset(
    {
        "requests.decide",
        "requests.final_decision",
        "transport.decide",
        "equipment.decide",
        "careers.launch",
        "careers.evaluate",
        "interventions.decide",
    }
)

OWNER_FIELDS = ("requester", "employee", "recipient", "author", "reported_by")


def column(employee) -> int:
    from apps.people.models import Role

    if employee.role == Role.ADMIN:
        return ADMIN_COL
    if employee.role == Role.HR:
        return HR_COL
    if employee.has_reports:
        return MANAGER_COL
    return EMPLOYEE_COL


def scope(employee, action: str):
    """Portée de l'action pour cette personne (None si interdite)."""
    if employee is None:
        return NONE
    try:
        rule = RULES[action]
    except KeyError as exc:
        raise KeyError(f"Action de permission inconnue : {action}") from exc
    return rule[column(employee)]


def owner_of(obj):
    """Personne à qui appartient l'objet (fiche, demande, entretien…)."""
    from apps.people.models import Employee

    if isinstance(obj, Employee):
        return obj
    for name in OWNER_FIELDS:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise TypeError(f"Propriétaire introuvable pour {type(obj).__name__}")


def _in_scope(employee, owner, reach) -> bool:
    if reach == ALL:
        return True
    if reach == SELF:
        return owner.pk == employee.pk
    if reach == TEAM:
        return owner.pk == employee.pk or owner.manager_id == employee.pk
    if reach == SERVICE:
        same_service = employee.service_id is not None and owner.service_id == employee.service_id
        return owner.pk == employee.pk or same_service or owner.manager_id == employee.pk
    return False


def can(employee, action: str, obj=None) -> bool:
    """L'action est-elle permise, globalement (obj=None) ou sur cet objet ?"""
    reach = scope(employee, action)
    if reach is NONE:
        return False
    if obj is None:
        return True
    if getattr(obj, "company_id", employee.company_id) != employee.company_id:
        return False
    owner = owner_of(obj)
    if action in SELF_FORBIDDEN and owner.pk == employee.pk:
        return False
    return _in_scope(employee, owner, reach)


def scope_queryset(employee, queryset: QuerySet, action: str, owner_field: str = "") -> QuerySet:
    """Restreint un queryset à la portée de l'action. `owner_field` : chemin vers la fiche
    propriétaire (« requester », « employee »…) ; vide si le queryset porte sur Employee."""
    reach = scope(employee, action)
    prefix = f"{owner_field}__" if owner_field else ""
    me = Q(**{f"{owner_field or 'pk'}": employee.pk}) if owner_field else Q(pk=employee.pk)
    team = Q(**{f"{prefix}manager": employee.pk})
    if reach == ALL:
        result = queryset
    elif reach == SELF:
        result = queryset.filter(me)
    elif reach == TEAM:
        result = queryset.filter(me | team)
    elif reach == SERVICE:
        same_service = (
            Q(**{f"{prefix}service": employee.service_id}) if employee.service_id else Q(pk__in=[])
        )
        result = queryset.filter(me | same_service | team)
    else:
        return queryset.none()
    if action in SELF_FORBIDDEN:
        result = result.exclude(me)
    return result
