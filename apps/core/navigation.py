"""Menu latéral, repris de la constante NAV du prototype.

Chaque entrée indique le module qui la conditionne (`module`, valeurs de CompanyModule) et
les profils autorisés (`roles`, None = tous). Le filtrage par module activé et par profil
est branché au lot 1 ; une entrée dont la route n'existe pas encore n'est pas affichée.
"""

from dataclasses import dataclass, field, replace

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str
    url_name: str | None = None
    module: str | None = None
    roles: tuple[str, ...] | None = None
    soon: bool = False
    # Rempli au rendu
    url: str | None = None
    active: bool = False
    count: int = 0


@dataclass(frozen=True)
class NavGroup:
    label: str
    items: tuple[NavItem, ...] = field(default_factory=tuple)


NAV: tuple[NavGroup, ...] = (
    NavGroup(
        "",
        (
            NavItem("dashboard", _("Tableau de bord"), "dash", "dashboard:home"),
            NavItem("people", _("Annuaire"), "users", "people:list", module="people"),
            NavItem("planning", _("Planning"), "cal", "planning:week", module="planning"),
        ),
    ),
    NavGroup(
        _("Demandes"),
        (
            NavItem("telework", _("Télétravail"), "home", "approvals:telework", "telework"),
            NavItem("summer_leave", _("Congés estivaux"), "sun", "approvals:leave", "summer_leave"),
            NavItem("on_call", _("Astreintes"), "clock", "approvals:on_call", "on_call"),
            NavItem("transport", _("Transport"), "ticket", "approvals:transport", "transport"),
            NavItem("equipment", _("Matériel"), "laptop", "equipment:home", "equipment"),
        ),
    ),
    NavGroup(
        _("Activité"),
        (
            NavItem(
                "interventions",
                _("Suivi d'intervention"),
                "tool",
                "interventions:list",
                "interventions",
            ),
        ),
    ),
    NavGroup(
        _("Talents"),
        (
            NavItem("careers", _("Carrière et évaluations"), "up", "careers:home", "careers"),
            NavItem("surveys", _("Questionnaires"), "clip", "surveys:list", "surveys"),
            NavItem("workload", _("Plan de charge"), "chart", soon=True),
            NavItem(
                "recruitment",
                _("Recrutement"),
                "brief",
                soon=True,
                roles=("manager", "hr", "admin"),
            ),
        ),
    ),
    NavGroup(
        _("Entreprise"),
        (
            NavItem(
                "announcements",
                _("Communication interne"),
                "mega",
                "announcements:list",
                "announcements",
            ),
            NavItem(
                "planning_export",
                _("Export du planning"),
                "dl",
                "planning:export",
                "planning",
            ),
            NavItem(
                "administration",
                _("Administration"),
                "set",
                "administration:home",
                roles=("admin",),
            ),
        ),
    ),
)


def _resolve(url_name: str | None) -> str | None:
    if not url_name:
        return None
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


def build_nav(current: str | None = None, counts: dict[str, int] | None = None):
    """Menu réel : seules les entrées dont la route existe sont rendues.

    Les entrées « Bientôt » sont affichées sans lien (décision du lot 1 sur la page
    d'information). Le filtrage par module et par profil arrive au lot 1."""
    counts = counts or {}
    groups = []
    for group in NAV:
        items = []
        for item in group.items:
            url = _resolve(item.url_name)
            if url is None and not item.soon:
                continue
            items.append(
                replace(item, url=url, active=item.key == current, count=counts.get(item.key, 0))
            )
        if items:
            groups.append(NavGroup(group.label, tuple(items)))
    return groups


def build_demo_nav(current: str | None = None, counts: dict[str, int] | None = None):
    """Menu complet pour le guide de style (/dev/styleguide/, développement uniquement)."""
    counts = counts or {}
    return [
        NavGroup(
            group.label,
            tuple(
                replace(
                    item,
                    url=None if item.soon else "#",
                    active=item.key == current,
                    count=counts.get(item.key, 0),
                )
                for item in group.items
            ),
        )
        for group in NAV
    ]
