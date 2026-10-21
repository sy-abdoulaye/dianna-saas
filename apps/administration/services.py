"""Administration de l'entreprise (docs/modules/04-administration.md). Toutes les actions
de l'onglet sont journalisées."""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core import audit
from apps.core.csv_export import csv_content
from apps.core.files import delete_after_commit, file_writes
from apps.core.models import AuditLog, Company, Service, Site
from apps.people.models import Employee, EmployeeStatus

STRUCTURES = {
    "services": (Service, "service", gettext_lazy("Service"), gettext_lazy("service")),
    "sites": (Site, "site", gettext_lazy("Site"), gettext_lazy("site")),
}


class AdministrationError(Exception):
    def __init__(self, message):
        super().__init__(str(message))
        self.message = message


def update_company(
    company: Company, data: dict, *, actor, logo=None, remove_logo=False, request=None
) -> list[str]:
    """Paramètres de l'entreprise ; logo écrit avant l'UPDATE, supprimé en cas d'échec,
    ancien logo supprimé après la validation (L5-18)."""
    with file_writes() as files, transaction.atomic():
        return _update_company(
            company,
            data,
            actor=actor,
            logo=logo,
            remove_logo=remove_logo,
            request=request,
            files=files,
        )


def _update_company(company, data, *, actor, logo, remove_logo, request, files):
    company = Company.objects.select_for_update().get(pk=company.pk)
    changed = [name for name, value in data.items() if getattr(company, name) != value]
    for name in changed:
        setattr(company, name, data[name])
    if logo is not None:
        delete_after_commit(company.logo.name)
        files.save(company.logo, logo)
        changed.append("logo")
    elif remove_logo and company.logo:
        delete_after_commit(company.logo.name)
        company.logo = None
        changed.append("logo")
    if changed:
        company.save()
        audit.log(
            "company.settings_updated",
            _("Paramètres de l'entreprise modifiés"),
            actor=actor,
            target=company,
            request=request,
        )
    return changed


def usage(kind: str, obj) -> int:
    """Nombre de collaborateurs en poste rattachés à ce service ou à ce site."""
    _model, field, _label, _lower = STRUCTURES[kind]
    return Employee.objects.filter(**{field: obj}).exclude(status=EmployeeStatus.LEFT).count()


def add_structure(kind: str, name: str, *, actor, request=None, alsace_moselle=False):
    model, _field, label, _lower = STRUCTURES[kind]
    extra = {"alsace_moselle": alsace_moselle} if hasattr(model, "alsace_moselle") else {}
    obj = model.objects.create(name=name, **extra)
    audit.log(
        f"company.{kind}_added",
        _("%(label)s ajouté : %(name)s") % {"label": label, "name": name},
        actor=actor,
        target=obj,
        request=request,
    )
    return obj


def rename_structure(kind: str, obj, name: str, *, actor, request=None, alsace_moselle=None):
    old = obj.name
    obj.name = name
    fields = ["name", "updated_at"]
    changes_holidays = (
        alsace_moselle is not None
        and hasattr(obj, "alsace_moselle")
        and obj.alsace_moselle != alsace_moselle
    )
    if changes_holidays:
        obj.alsace_moselle = alsace_moselle
        fields.append("alsace_moselle")
        audit.log(
            "company.site_holidays_changed",
            (
                _("Jours fériés d'Alsace-Moselle activés : %(name)s")
                if alsace_moselle
                else _("Jours fériés d'Alsace-Moselle désactivés : %(name)s")
            )
            % {"name": name},
            actor=actor,
            target=obj,
            request=request,
        )
    obj.save(update_fields=fields)
    if old == name:
        return
    audit.log(
        f"company.{kind}_renamed",
        _("%(old)s renommé en %(new)s") % {"old": old, "new": name},
        actor=actor,
        target=obj,
        request=request,
    )


@transaction.atomic
def delete_structure(kind: str, obj, *, actor, request=None):
    """Impossible tant que des fiches y sont rattachées (y compris des fiches parties, que
    la base protège : RESTRICT)."""
    _model, field, _label, _lower = STRUCTURES[kind]
    if Employee.objects.filter(**{field: obj}).exists():
        raise AdministrationError(_("Suppression impossible : des fiches y sont rattachées."))
    name = obj.name
    obj.delete()
    audit.log(
        f"company.{kind}_deleted",
        _("%(name)s supprimé") % {"name": name},
        actor=actor,
        request=request,
    )


def journal(queryset, *, q="", start=None, end=None):
    entries = queryset.select_related("actor")
    if start:
        entries = entries.filter(created_at__date__gte=start)
    if end:
        entries = entries.filter(created_at__date__lte=end)
    if q:
        from django.db.models import Q

        entries = entries.filter(
            Q(summary__icontains=q)
            | Q(actor__first_name__icontains=q)
            | Q(actor__last_name__icontains=q)
            | Q(action__icontains=q)
        )
    return entries


def export_journal_csv(*, q, start, end, actor, request=None) -> str:
    """CSV de la période (apps.core.csv_export : point-virgule, BOM, cellules neutralisées).
    L'export lui-même est journalisé."""
    entries = journal(AuditLog.objects.all(), q=q, start=start, end=end).order_by("created_at")

    def rows():
        for entry in entries:
            moment = timezone.localtime(entry.created_at)
            yield [
                moment.strftime("%d/%m/%Y"),
                moment.strftime("%H:%M"),
                entry.actor.full_name if entry.actor else _("Dianna"),
                entry.action,
                entry.summary,
            ]

    content = csv_content([_("Date"), _("Heure"), _("Personne"), _("Action"), _("Résumé")], rows())
    audit.log(
        "audit.exported",
        _("Journal exporté du %(start)s au %(end)s")
        % {"start": start.strftime("%d/%m/%Y"), "end": end.strftime("%d/%m/%Y")},
        actor=actor,
        request=request,
    )
    return content


# ---------- Fermetures (T-16) ----------

CLOSURE_PAST = gettext_lazy("La date est passée.")
CLOSURE_DUPLICATE = gettext_lazy("Une fermeture existe déjà ce jour-là pour ce périmètre.")


class ClosureError(AdministrationError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def affected_telework(closure):
    """Demandes de télétravail en attente ou validées le jour d'une fermeture (L4-03)."""
    from apps.approvals.models import RequestStatus, TeleworkRequest

    requests = TeleworkRequest.objects.filter(
        date=closure.date, status__in=(RequestStatus.PENDING, RequestStatus.APPROVED)
    ).select_related("requester")
    if closure.site_id:
        requests = requests.filter(requester__site_id=closure.site_id)
    return list(requests.order_by("requester__last_name", "requester__first_name"))


def closure_scope(closure) -> str:
    if closure.site_id:
        return _("site de %(name)s") % {"name": closure.site.name}
    return _("toute l'entreprise")


@transaction.atomic
def add_closure(*, day, label, site, actor, request=None):
    """Ajoute une fermeture. Contrôles (date passée, doublon) faits ici, sous verrou de
    l'entreprise : deux ajouts simultanés passent l'un après l'autre (A3-02). Les demandes de
    télétravail déjà faites ce jour-là restent telles quelles (L4-03) ; leur liste, calculée
    sous le même verrou, est envoyée aux RH."""
    from django.db import IntegrityError
    from django.urls import reverse
    from django.utils.formats import date_format

    from apps.agenda.models import Closure
    from apps.core import notifications
    from apps.core.tenancy import get_current_company
    from apps.people.models import IN_POST_STATUSES, Role

    Company.objects.select_for_update().get(pk=get_current_company().pk)
    if day < timezone.localdate():
        raise ClosureError("date", CLOSURE_PAST)
    if Closure.objects.filter(date=day, site=site).exists():
        raise ClosureError("date", CLOSURE_DUPLICATE)
    try:
        with transaction.atomic():
            closure = Closure.objects.create(date=day, label=label, site=site)
    except IntegrityError as exc:
        raise ClosureError("date", CLOSURE_DUPLICATE) from exc
    when = date_format(day, "j F Y")
    audit.log(
        "company.closure_added",
        _("Fermeture ajoutée : %(label)s, le %(day)s (%(scope)s)")
        % {"label": label, "day": when, "scope": closure_scope(closure)},
        actor=actor,
        target=closure,
        request=request,
    )
    concerned = affected_telework(closure)
    if concerned:
        names = ", ".join(r.requester.full_name for r in concerned)
        text = _(
            "Fermeture du %(day)s (%(scope)s) : %(n)s demande(s) de télétravail concernée(s) : "
            "%(names)s."
        ) % {"day": when, "scope": closure_scope(closure), "n": len(concerned), "names": names}
        if len(text) > 255:
            text = text[:254] + "…"
        url = reverse("administration:closures") + f"#fermeture-{closure.pk}"
        hr = Employee.objects.filter(
            role=Role.HR, status__in=IN_POST_STATUSES, user__is_active=True
        ).select_related("user")
        recipients = list(hr) or list(
            Employee.objects.filter(
                role=Role.ADMIN, status__in=IN_POST_STATUSES, user__is_active=True
            ).select_related("user")
        )
        for person in recipients:
            notifications.notify(person, text, url=url, kind="info")
    return closure, concerned


@transaction.atomic
def delete_closure(closure, *, actor, request=None):
    from django.utils.formats import date_format

    summary = _("Fermeture supprimée : %(label)s, le %(day)s (%(scope)s)") % {
        "label": closure.label,
        "day": date_format(closure.date, "j F Y"),
        "scope": closure_scope(closure),
    }
    closure.delete()
    audit.log("company.closure_deleted", summary, actor=actor, request=request)
