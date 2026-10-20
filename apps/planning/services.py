"""Planning (docs/modules/06-planning.md) : calcul de la grille et des exports.

Une seule source : `CalendarEvent` (L1-07). Une case vaut, par ordre de priorité :
- « — » avant la date d'arrivée ;
- vide le week-end ; le libellé du jour férié ou de la fermeture ces jours-là ;
- Congés, puis Télétravail, sinon Sur site ;
l'astreinte se cumule (repère « A »), y compris le week-end et les jours non ouvrés (L4-01).

Requêtes par grille, quel que soit l'effectif : les personnes de la page, leurs événements de
la période, les fermetures et les sites d'Alsace-Moselle. Jamais de requête par case.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import pgettext_lazy

from apps.agenda.days import DayOffs, days
from apps.agenda.models import CalendarEvent
from apps.core import permissions
from apps.people.models import IN_POST_STATUSES, Employee

PER_PAGE = 50
MAX_EXPORT_DAYS = 92  # 3 mois au plus par export

SITE, TELEWORK, LEAVE, WEEKEND, DAY_OFF, NOT_YET = "site", "tt", "cp", "we", "off", "none"
LABELS = {
    SITE: pgettext_lazy("planning", "Sur site"),
    TELEWORK: pgettext_lazy("planning", "Télétravail"),
    LEAVE: pgettext_lazy("planning", "Congés"),
    WEEKEND: pgettext_lazy("planning", "Week-end"),
    NOT_YET: pgettext_lazy("planning", "Pas encore arrivé"),
}
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

    @property
    def label(self) -> str:
        if self.state == DAY_OFF:
            text = self.day_off_label
        else:
            text = str(LABELS[self.state])
            if self.pending:
                text = _("%(state)s (en attente)") % {"state": text}
        if self.on_call:
            on_call = _("astreinte en attente") if self.on_call_pending else _("astreinte")
            text = f"{text}, {on_call}" if text else on_call.capitalize()
        return text

    @property
    def state_label(self) -> str:
        """Libellé de l'état principal, sans l'astreinte (repère « A » à part)."""
        if self.state == DAY_OFF:
            return self.day_off_label
        text = str(LABELS[self.state])
        return _("%(state)s (en attente)") % {"state": text} if self.pending else text

    @property
    def letter(self) -> str:
        return LETTERS[self.state]

    @property
    def export_value(self) -> str:
        return self.label


@dataclass
class Row:
    employee: Employee
    cells: list
    is_me: bool = False


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
        return date_format(first, "F Y")
    return _("Semaine du %(start)s au %(end)s") % {
        "start": date_format(first, "j N"),
        "end": date_format(last, "j F Y"),
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


# ---------- Cases ----------


def _events(employee_ids, first, last):
    """{(employee_id, jour): {type: statut}} pour la période, en une requête."""
    found = {}
    rows = CalendarEvent.objects.filter(
        employee_id__in=employee_ids, start__lte=last, end__gte=first
    ).values_list("employee_id", "kind", "start", "end", "status")
    for employee_id, kind, start, end, status in rows:
        for day in days(max(start, first), min(end, last)):
            found.setdefault((employee_id, day), {})[kind] = status
    return found


def build_rows(people, first, last, *, viewer=None, can_declare=False, today=None):
    people = list(people)
    events = _events([p.pk for p in people], first, last)
    offs = DayOffs(first, last)
    period = list(days(first, last))
    rows = []
    for person in people:
        is_me = viewer is not None and person.pk == viewer.pk
        cells = [
            _cell(person, day, events.get((person.pk, day), {}), offs, is_me and can_declare, today)
            for day in period
        ]
        rows.append(Row(person, cells, is_me))
    return rows


def _cell(person, day, kinds, offs, can_declare, today):
    on_call_status = kinds.get(CalendarEvent.Kind.ON_CALL)
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
            cell.state = state
            cell.pending = kinds[kind] == CalendarEvent.Status.PENDING
            return cell
    cell.clickable = can_declare and today is not None and day >= today
    return cell


def present_today(people, today) -> int:
    """Personnes du périmètre filtré sur site aujourd'hui (pied du planning, tableau de bord)."""
    return count_today(people, today)[SITE]


def count_today(people, today) -> dict:
    """Répartition du jour : sur site, télétravail, congés, astreinte (3 requêtes)."""
    people = list(people.values_list("pk", "site_id", "arrival_date"))
    counts = {SITE: 0, TELEWORK: 0, LEAVE: 0, "on_call": 0}
    if not people:
        return counts
    kinds = {}
    for employee_id, kind in CalendarEvent.objects.filter(
        employee_id__in=[p[0] for p in people], start__lte=today, end__gte=today
    ).values_list("employee_id", "kind"):
        kinds.setdefault(employee_id, set()).add(kind)
    offs = DayOffs(today, today)
    for pk, site_id, arrival in people:
        mine = kinds.get(pk, set())
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


def grid(viewer, *, view, anchor, page=1, q="", service=None, site=None, can_declare=False, today):
    first, last = month_of(anchor) if view == "mois" else week_of(anchor)
    people = people_in_scope(viewer, q=q, service=service, site=site)
    others = ordered(people.exclude(pk=viewer.pk), viewer)
    page_obj = Paginator(others, PER_PAGE).get_page(page)
    shown = list(page_obj.object_list)
    me = people.filter(pk=viewer.pk).first()
    if me is not None:
        shown.insert(0, me)  # « (vous) » en tête de chaque page
    result = Grid(first, last, list(days(first, last)), page_obj=page_obj)
    result.rows = build_rows(
        shown, first, last, viewer=viewer, can_declare=can_declare, today=today
    )
    result.total = page_obj.paginator.count + (1 if me is not None else 0)
    result.present_today = present_today(people, today)
    return result


# ---------- Export ----------


def export_rows(viewer, first, last, *, service=None):
    """Lignes de l'export : jours ouvrés (lundi à vendredi) de la période, périmètre de la
    personne. Le service choisi ne fait que restreindre ce périmètre."""
    people = ordered(people_in_scope(viewer, service=service), viewer)
    working = [day for day in days(first, last) if day.weekday() < 5]
    rows = build_rows(people, first, last)
    header = [_("Collaborateur"), _("Service"), _("Site")] + [
        date_format(day, "D j/m") for day in working
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
