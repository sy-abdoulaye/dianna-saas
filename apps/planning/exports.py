"""Fichiers d'export du planning : CSV, Excel, iCalendar, PDF (T-15, L4-05, L4-06).

Le périmètre est celui de la vue (services.people_in_scope) ; l'export est journalisé avec la
période, le format et le périmètre, sans nom de personne (CLAUDE.md, règle 5)."""

from django.utils.translation import gettext as _

from apps.agenda.models import CalendarEvent
from apps.core import audit
from apps.core.csv_export import csv_content
from apps.core.dates import day_stamp, format_date
from apps.core.ics_export import ICS_CONTENT_TYPE, IcsEvent, ics_content
from apps.core.pdf import PDF_CONTENT_TYPE, render_pdf
from apps.core.xlsx_export import XLSX_CONTENT_TYPE, Styled, xlsx_content
from apps.planning import services

CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
STATE_TOKENS = {
    services.SITE: ("site-bg", "site-ink"),
    services.TELEWORK: ("tel-bg", "tel-ink"),
    services.LEAVE: ("cng-bg", "cng-ink"),
    services.DAY_OFF: ("track", "ink-2"),
    services.NOT_YET: ("", "ink-3"),
}


def period_text(first, last) -> str:
    return _("du %(start)s au %(end)s") % {
        "start": format_date(first, "long"),
        "end": format_date(last, "long"),
    }


def build(viewer, *, first, last, service, fmt, people=None):
    """(contenu, type MIME, nom de fichier). `people` : personnes retenues pour le PDF (une
    page du planning au plus, L4-17). L'entreprise est celle de la personne."""
    company = viewer.company
    header, lines, rows, working = services.export_rows(
        viewer, first, last, service=service, people=people
    )
    stem = f"planning-{day_stamp(first)}-{day_stamp(last)}"
    if fmt == "csv":
        return csv_content(header, lines), CSV_CONTENT_TYPE, f"{stem}.csv"
    if fmt == "xlsx":
        return _xlsx(header, rows, working), XLSX_CONTENT_TYPE, f"{stem}.xlsx"
    if fmt == "ics":
        return _ics(rows, first, last, company), ICS_CONTENT_TYPE, f"{stem}.ics"
    return _pdf(rows, first, last, company), PDF_CONTENT_TYPE, f"{stem}.pdf"


def _xlsx(header, rows, working):
    def lines():
        for row in rows:
            person = row.employee
            by_day = {cell.day: cell for cell in row.cells}
            values = [
                person.full_name,
                person.service.name if person.service else "",
                person.site.name if person.site else "",
            ]
            for day in working:
                cell = by_day[day]
                fill, ink = STATE_TOKENS.get(cell.state, ("", ""))
                values.append(Styled(cell.export_value, fill, ink))
            yield values

    widths = [28, 18, 14] + [16] * len(working)
    return xlsx_content(_("Planning"), header, lines(), freeze="D2", widths=widths)


def _ics(rows, first, last, company):
    """Un événement par absence et par télétravail (pas les astreintes), coupé à la période
    demandée. Même règle de confidentialité que la vue (L4-16) : pour un collègue, seulement
    les demandes validées, et « Absent » pour tout congé."""
    people = {row.employee.pk: row for row in rows}
    events = list(
        CalendarEvent.objects.filter(
            employee_id__in=list(people),
            kind__in=(CalendarEvent.Kind.LEAVE, CalendarEvent.Kind.TELEWORK),
            start__lte=last,
            end__gte=first,
        ).order_by("start", "employee_id")
    )
    labels = services.leave_types(
        [e.source_id for e in events if e.kind == CalendarEvent.Kind.LEAVE]
    )
    items = []
    for event in events:
        row = people[event.employee_id]
        pending = event.status == CalendarEvent.Status.PENDING
        if pending and not row.full:
            continue
        if event.kind == CalendarEvent.Kind.LEAVE:
            what = labels.get(event.source_id) if row.full else str(services.ABSENT)
            what = what or event.get_kind_display()
        else:
            what = event.get_kind_display()
        items.append(
            IcsEvent(
                uid=f"{event.source_type}-{event.source_id}@{company.slug}.dianna",
                start=max(event.start, first),
                end=min(event.end, last),
                summary=f"{what} · {row.employee.full_name}",
                tentative=pending,
            )
        )
    return ics_content(items, name=_("Planning %(company)s") % {"company": company.name})


def _pdf(rows, first, last, company):
    """A4 paysage, une page par semaine (lundi à vendredi)."""
    return render_pdf("planning/pdf.html", pdf_context(rows, first, last, company), company=company)


def pdf_context(rows, first, last, company):
    weeks = []
    for start in services.days(first, last):
        if start.weekday() != 0 and start != first:
            continue
        week = [
            d
            for d in services.days(start, min(last, services.week_of(start)[1]))
            if d.weekday() < 5
        ]
        if week:
            weeks.append(week)
    pages = []
    for week in weeks:
        wanted = set(week)
        pages.append(
            {
                "days": week,
                "title": services.period_title("semaine", *services.week_of(week[0])),
                "rows": [(row, [cell for cell in row.cells if cell.day in wanted]) for row in rows],
            }
        )
    return {"company": company, "pages": pages, "period": period_text(first, last)}


def log_export(*, viewer, first, last, fmt_label, scope_label, request=None):
    summary = _("%(what)s %(period)s, %(fmt)s, %(scope)s") % {
        "what": _("Export du planning"),
        "period": period_text(first, last),
        "fmt": fmt_label,
        "scope": scope_label,
    }
    audit.log("planning.exported", summary, actor=viewer, request=request)
