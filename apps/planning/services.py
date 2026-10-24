"""Planning (docs/modules/06-planning.md) : calcul de la grille et des exports.

Une seule source : `CalendarEvent` (L1-07). Une case vaut, par ordre de priorité :
- « — » avant la date d'arrivée ;
- vide le week-end ; le libellé du jour férié ou de la fermeture ces jours-là ;
- Congés, puis Télétravail, sinon Sur site ;
l'astreinte se cumule (repère « A »), y compris le week-end et les jours non ouvrés (L4-01).

Confidentialité (minimisation, L4-16) : chacun voit tout ce qui le concerne ; le manager pour
son équipe directe, les RH et l'administrateur voient le type exact d'absence et les demandes
en attente ; un collègue du périmètre ne voit que les demandes validées, et « Absent » pour
tout congé, quel que soit son type. La règle s'applique à la vue, à l'aperçu et aux exports.

Requêtes par grille, quel que soit l'effectif : les personnes de la page, leurs événements de
la période, les fermetures et les sites d'Alsace-Moselle. Jamais de requête par case.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils.translation import gettext as _
from django.utils.translation import pgettext_lazy

from apps.agenda.days import DayOffs, days
from apps.agenda.models import CalendarEvent
from apps.approvals.models import LeaveRequest
from apps.core import permissions
from apps.core.dates import format_date
from apps.people.models import IN_POST_STATUSES, Employee, Role

PER_PAGE = 50
MAX_EXPORT_DAYS = 92  # 3 mois au plus par export
MAX_PDF_DAYS = 31  # PDF : un mois au plus (L4-17)
MAX_PDF_PEOPLE = PER_PAGE  # PDF : une page du planning au plus (L4-17)
# Bornes des dates acceptées (planning et exports) : au-delà, retour à aujourd'hui ou erreur
# de formulaire, jamais d'erreur 500 (L4-18).
MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)

SITE, TELEWORK, LEAVE, WEEKEND, DAY_OFF, NOT_YET = "site", "tt", "cp", "we", "off", "none"
LABELS = {
    SITE: pgettext_lazy("planning", "Sur site"),
    TELEWORK: pgettext_lazy("planning", "Télétravail"),
    LEAVE: pgettext_lazy("planning", "Congés"),
    WEEKEND: pgettext_lazy("planning", "Week-end"),
    NOT_YET: pgettext_lazy("planning", "Pas encore arrivé"),
}
ABSENT = pgettext_lazy("planning", "Absent")
LETTERS = {SITE: "S", TELEWORK: "T", LEAVE: "C", NOT_YET: "—", DAY_OFF: "F", WEEKEND: ""}


@dataclass
class Cell:
    day: date
    state: str
    pending: bool = False
    on_call: bool = False
    on_call_pending: bool = False
    day_off_label: str = ""
    clickable: bool = False
    leave_label: str = ""  # « Congés d'été », « Autre absence » ou « Absent » (L4-16)

    @property
    def label(self) -> str:
        text = self.state_label
        if self.on_call:
            on_call = _("astreinte en attente") if self.on_call_pending else _("astreinte")
            text = f"{text}, {on_call}" if text else on_call.capitalize()
        return text

    @property
    def state_label(self) -> str:
        """Libellé de l'état principal, sans l'astreinte (repère « A » à part)."""
        if self.state == DAY_OFF:
            return self.day_off_label
        text = (
            self.leave_label
            if self.state == LEAVE and self.leave_label
            else str(LABELS[self.state])
        )
        return _("%(state)s (en attente)") % {"state": text} if self.pending else text

    @property
    def letter(self) -> str:
        if self.state == LEAVE and self.leave_label == str(ABSENT):
            return "Ab"
        return LETTERS[self.state]

    @property
    def export_value(self) -> str:
        return self.label


@dataclass
class Row:
    employee: Employee
    cells: list
    is_me: bool = False
    full: bool = True  # détail visible (L4-16)


@dataclass(frozen=True)
class PeopleFilter:
    """Filtres de la grille (recherche, service, site) : ils ne font que restreindre le
    périmètre de la personne."""

    q: str = ""
    service: int | None = None
    site: int | None = None


NO_FILTER = PeopleFilter()


@dataclass(frozen=True)
class GridPage:
    """Page affichée et déclaration depuis la grille (sa propre ligne, module Télétravail)."""

    number: int | str | None = 1
    can_declare: bool = False


FIRST_PAGE = GridPage()


@dataclass
class Grid:
    first: date
    last: date
    days: list
    rows: list = field(default_factory=list)
    page_obj: object = None
    total: int = 0
    present_today: int = 0


# ---------- Période ----------


def week_of(anchor: date) -> tuple[date, date]:
    monday = anchor - timedelta(days=anchor.weekday())
    return monday, monday + timedelta(days=6)


def month_of(anchor: date) -> tuple[date, date]:
    last_day = calendar.monthrange(anchor.year, anchor.month)[1]
    return anchor.replace(day=1), anchor.replace(day=last_day)


def shift(anchor: date, view: str, step: int) -> date:
    if view == "mois":
        month = anchor.month - 1 + step
        return date(anchor.year + month // 12, month % 12 + 1, 1)
    return anchor + timedelta(days=7 * step)


def period_title(view: str, first: date, last: date) -> str:
    if view == "mois":
        return format_date(first, "month")
    return _("Semaine du %(start)s au %(end)s") % {
        "start": format_date(first, "short"),
        "end": format_date(last, "long"),
    }


# ---------- Périmètre ----------


def people_in_scope(viewer, *, q="", service=None, site=None):
    """Personnes visibles : salarié, son service ; manager, son service et son équipe
    (L1-06) ; RH et administrateur, toute l'entreprise. Les filtres ne font que restreindre :
    un identifiant de service hors périmètre dans l'URL ne montre personne de plus."""
    people = permissions.scope_queryset(
        viewer, Employee.objects.filter(status__in=IN_POST_STATUSES), "planning.view"
    )
    if q:
        people = people.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if service:
        people = people.filter(service_id=service)
    if site:
        people = people.filter(site_id=site)
    return people.select_related("site", "service")


def ordered(people, viewer):
    """La personne connectée en premier, puis par nom."""
    return people.annotate(
        me_first=Case(
            When(pk=viewer.pk, then=Value(0)), default=Value(1), output_field=IntegerField()
        )
    ).order_by("me_first", "last_name", "first_name", "pk")


# ---------- Confidentialité (L4-16) ----------


def sees_details(viewer, person) -> bool:
    """Type exact d'absence et demandes en attente : soi, son équipe directe, RH et admin.
    Sans `viewer` (calculs internes), tout est visible."""
    if viewer is None or person.pk == viewer.pk:
        return True
    if viewer.role in (Role.HR, Role.ADMIN):
        return True
    return person.manager_id == viewer.pk


def leave_types(source_ids) -> dict:
    """{id de la demande de congé: libellé du type} en une requête."""
    if not source_ids:
        return {}
    return {
        pk: str(LeaveRequest.LeaveType(leave_type).label)
        for pk, leave_type in LeaveRequest.objects.filter(pk__in=source_ids).values_list(
            "pk", "leave_type"
        )
    }


# ---------- Cases ----------


def _events(employee_ids, first, last):
    """{(employee_id, jour): {type: (statut, libellé du congé)}} pour la période (2 requêtes)."""
    found: dict[tuple, dict] = {}
    rows = list(
        CalendarEvent.objects.filter(
            employee_id__in=employee_ids, start__lte=last, end__gte=first
        ).values_list("employee_id", "kind", "start", "end", "status", "source_id")
    )
    labels = leave_types([r[5] for r in rows if r[1] == CalendarEvent.Kind.LEAVE])
    for employee_id, kind, start, end, status, source_id in rows:
        label = labels.get(source_id, "") if kind == CalendarEvent.Kind.LEAVE else ""
        for day in days(max(start, first), min(end, last)):
            found.setdefault((employee_id, day), {})[kind] = (status, label)
    return found


def build_rows(people, first, last, *, viewer=None, can_declare=False, today=None):
    people = list(people)
    events = _events([p.pk for p in people], first, last)
    offs = DayOffs(first, last)
    period = list(days(first, last))
    rows = []
    for person in people:
        is_me = viewer is not None and person.pk == viewer.pk
        full = sees_details(viewer, person)
        cells = [
            _cell(
                person,
                day,
                events.get((person.pk, day), {}),
                offs,
                today if is_me and can_declare else None,
                full,
            )
            for day in period
        ]
        rows.append(Row(person, cells, is_me, full))
    return rows


def _cell(person, day, kinds, offs, declarable_from, full=True):
    """`declarable_from` : premier jour où la personne peut déclarer du télétravail depuis la
    case (aujourd'hui, sur sa propre ligne), sinon None."""
    if not full:
        # Collègue : seulement les demandes validées.
        kinds = {
            kind: value
            for kind, value in kinds.items()
            if value[0] == CalendarEvent.Status.APPROVED
        }
    on_call_status = kinds.get(CalendarEvent.Kind.ON_CALL, (None, ""))[0]
    cell = Cell(
        day,
        SITE,
        on_call=on_call_status is not None,
        on_call_pending=on_call_status == CalendarEvent.Status.PENDING,
    )
    if person.arrival_date and day < person.arrival_date:
        cell.state, cell.on_call = NOT_YET, False
        return cell
    if day.weekday() >= 5:
        cell.state = WEEKEND
        return cell
    off = offs.get(day, person.site_id)
    if off is not None:
        cell.state = DAY_OFF
        suffix = _("férié") if off.kind == "holiday" else _("fermeture")
        cell.day_off_label = f"{off.label} ({suffix})"
        return cell
    for kind, state in ((CalendarEvent.Kind.LEAVE, LEAVE), (CalendarEvent.Kind.TELEWORK, TELEWORK)):
        if kind in kinds:
            status, label = kinds[kind]
            cell.state = state
            cell.pending = status == CalendarEvent.Status.PENDING
            if state == LEAVE:
                cell.leave_label = label if full else str(ABSENT)
            return cell
    cell.clickable = declarable_from is not None and day >= declarable_from
    return cell


def present_today(people, today, viewer=None) -> int:
    """Personnes du périmètre filtré sur site aujourd'hui (pied du planning)."""
    return count_today(people, today, viewer)[SITE]


def count_today(people, today, viewer=None) -> dict:
    """Répartition du jour : sur site, télétravail, congés, astreinte (3 requêtes).

    Même règle que les cases (L4-16, L4-20, `sees_details`) : pour une personne dont le
    regardeur ne voit pas le détail, seules les demandes validées comptent."""
    people = list(people.values_list("pk", "site_id", "arrival_date", "manager_id"))
    counts = {SITE: 0, TELEWORK: 0, LEAVE: 0, "on_call": 0}
    if not people:
        return counts
    kinds: dict[int, dict[str, str]] = {}
    for employee_id, kind, status in CalendarEvent.objects.filter(
        employee_id__in=[p[0] for p in people], start__lte=today, end__gte=today
    ).values_list("employee_id", "kind", "status"):
        kinds.setdefault(employee_id, {})[kind] = status
    offs = DayOffs(today, today)
    for pk, site_id, arrival, manager_id in people:
        person = Employee(pk=pk, manager_id=manager_id)
        full = sees_details(viewer, person)
        mine = {
            kind
            for kind, status in kinds.get(pk, {}).items()
            if full or status == CalendarEvent.Status.APPROVED
        }
        if CalendarEvent.Kind.ON_CALL in mine:
            counts["on_call"] += 1
        if (arrival and today < arrival) or today.weekday() >= 5 or offs.get(today, site_id):
            continue
        if CalendarEvent.Kind.LEAVE in mine:
            counts[LEAVE] += 1
        elif CalendarEvent.Kind.TELEWORK in mine:
            counts[TELEWORK] += 1
        else:
            counts[SITE] += 1
    return counts


def grid(viewer, *, view, anchor, today, filters=NO_FILTER, page=FIRST_PAGE) -> Grid:
    first, last = month_of(anchor) if view == "mois" else week_of(anchor)
    people = people_in_scope(viewer, q=filters.q, service=filters.service, site=filters.site)
    others = ordered(people.exclude(pk=viewer.pk), viewer)
    page_obj = Paginator(others, PER_PAGE).get_page(page.number)
    shown = list(page_obj.object_list)
    me = people.filter(pk=viewer.pk).first()
    if me is not None:
        shown.insert(0, me)  # « (vous) » en tête de chaque page
    result = Grid(first, last, list(days(first, last)), page_obj=page_obj)
    result.rows = build_rows(
        shown, first, last, viewer=viewer, can_declare=page.can_declare, today=today
    )
    result.total = page_obj.paginator.count + (1 if me is not None else 0)
    result.present_today = present_today(people, today, viewer)
    return result


# ---------- Export ----------


def in_bounds(day) -> bool:
    return day is not None and MIN_DATE <= day <= MAX_DATE


def export_people(viewer, *, service=None):
    return ordered(people_in_scope(viewer, service=service), viewer)


def export_rows(viewer, first, last, *, service=None, people=None):
    """Lignes de l'export : jours ouvrés (lundi à vendredi) de la période, périmètre de la
    personne. Le service choisi ne fait que restreindre ce périmètre. Les cases suivent la
    même règle de confidentialité que la vue (L4-16)."""
    if people is None:
        people = export_people(viewer, service=service)
    working = [day for day in days(first, last) if day.weekday() < 5]
    rows = build_rows(people, first, last, viewer=viewer)
    header = [_("Collaborateur"), _("Service"), _("Site")] + [
        format_date(day, "weekday_numeric") for day in working
    ]
    lines = []
    for row in rows:
        by_day = {cell.day: cell for cell in row.cells}
        person = row.employee
        lines.append(
            [
                person.full_name,
                person.service.name if person.service else "",
                person.site.name if person.site else "",
            ]
            + [by_day[day].export_value for day in working]
        )
    return header, lines, rows, working
