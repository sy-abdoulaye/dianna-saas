"""Import CSV des salariés (Administrateur, M-15, fiche annuaire).

Colonnes : prenom;nom;email;poste;service;site;manager_email;date_arrivee;contrat.
1. Lecture et contrôle ligne par ligne (rien n'est écrit) ;
2. Aperçu : erreurs bloquantes par ligne, services et sites inconnus à créer ;
3. Confirmation : tout ou rien, dans une transaction. Aucune ligne n'est importée tant qu'une
   erreur bloquante reste. Les invitations ne partent pas : l'administrateur les envoie depuis
   « Utilisateurs et profils ».
"""

import csv
import io
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models.functions import Lower
from django.utils.translation import gettext as _

from apps.core import audit
from apps.core.models import Service, Site
from apps.people.models import ContractType, Employee, EmployeeChange
from apps.people.services import status_for_arrival

COLUMNS = [
    "prenom",
    "nom",
    "email",
    "poste",
    "service",
    "site",
    "manager_email",
    "date_arrivee",
    "contrat",
]
REQUIRED = ["prenom", "nom", "email", "poste", "service", "site", "date_arrivee"]
MAX_ROWS = 1000
MAX_BYTES = 1024 * 1024
CONTRACTS = {
    "cdi": ContractType.CDI,
    "cdd": ContractType.CDD,
    "alternance": ContractType.APPRENTICESHIP,
    "stage": ContractType.INTERNSHIP,
}


class ImportFileError(Exception):
    def __init__(self, message):
        super().__init__(str(message))
        self.message = message


@dataclass
class ImportRow:
    line: int
    values: dict
    errors: list = field(default_factory=list)


@dataclass
class ImportPreview:
    rows: list
    new_services: list
    new_sites: list

    @property
    def error_count(self) -> int:
        return sum(1 for row in self.rows if row.errors)

    @property
    def is_valid(self) -> bool:
        return bool(self.rows) and self.error_count == 0

    def as_session(self) -> list:
        return [asdict(row) for row in self.rows]


UNREADABLE = _("Le fichier n'est pas lisible. Enregistrez-le en CSV UTF-8.")


def max_lengths() -> dict[str, int]:
    """Longueur maximale de chaque colonne, lue sur les modèles (fiche, service, site)."""
    employee = Employee._meta
    return {
        "prenom": employee.get_field("first_name").max_length,
        "nom": employee.get_field("last_name").max_length,
        "email": employee.get_field("email").max_length,
        "poste": employee.get_field("job_title").max_length,
        "service": Service._meta.get_field("name").max_length,
        "site": Site._meta.get_field("name").max_length,
        "manager_email": employee.get_field("email").max_length,
        "date_arrivee": 10,
        "contrat": 20,
    }


def _decode(raw: bytes) -> str:
    if b"\x00" in raw:
        # Fichier binaire (tableur .xlsx, UTF-16…) : PostgreSQL refuserait l'octet nul.
        raise ImportFileError(UNREADABLE)
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportFileError(UNREADABLE)


def parse_date(value: str) -> date | None:
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def read(uploaded) -> list[ImportRow]:
    if uploaded.size > MAX_BYTES:
        raise ImportFileError(_("Le fichier dépasse 1 Mo."))
    text = _decode(uploaded.read())
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    try:
        header = [(name or "").strip().lower() for name in (reader.fieldnames or [])]
        missing = [name for name in COLUMNS if name not in header]
        if missing:
            raise ImportFileError(
                _("Colonnes manquantes : %(cols)s. Attendu : %(all)s.")
                % {"cols": ", ".join(missing), "all": ";".join(COLUMNS)}
            )
        reader.fieldnames = header
        rows = []
        for raw in reader:
            values = {name: (raw.get(name) or "").strip() for name in COLUMNS}
            if not any(values.values()):
                continue
            rows.append(ImportRow(line=reader.line_num, values=values))
            if len(rows) > MAX_ROWS:
                raise ImportFileError(_("Le fichier dépasse 1 000 lignes."))
    except csv.Error as exc:
        # Champ de plus de 128 Ko, guillemets impossibles à lire… : jamais d'erreur 500.
        raise ImportFileError(
            _("Ligne %(line)s : le fichier n'est pas un CSV valide (champ trop long ou mal formé).")
            % {"line": reader.line_num + 1}  # line_num : dernière ligne lue sans erreur
        ) from exc
    if not rows:
        raise ImportFileError(_("Le fichier ne contient aucune ligne."))
    return rows


def check(rows: list[ImportRow]) -> ImportPreview:
    """Contrôle chaque ligne (entreprise courante) sans rien écrire."""
    existing = {
        email: name
        for email, name in Employee.objects.annotate(e=Lower("email")).values_list("e", "last_name")
    }
    by_email = {}
    for row in rows:
        email = row.values["email"].lower()
        if email:
            by_email.setdefault(email, []).append(row.line)
    services = {s.lower() for s in Service.objects.values_list("name", flat=True)}
    sites = {s.lower() for s in Site.objects.values_list("name", flat=True)}
    new_services, new_sites = {}, {}
    limits = max_lengths()
    for row in rows:
        values = row.values
        for name in REQUIRED:
            if not values[name]:
                row.errors.append(_("« %(col)s » est obligatoire.") % {"col": name})
        for name, limit in limits.items():
            if len(values[name]) > limit:
                row.errors.append(
                    _("Ligne %(line)s : « %(col)s » dépasse %(max)s caractères.")
                    % {"line": row.line, "col": name, "max": limit}
                )
        email = values["email"].lower()
        if email:
            try:
                validate_email(email)
            except ValidationError:
                row.errors.append(_("L'adresse e-mail n'est pas valide."))
            if email in existing:
                row.errors.append(_("Cette adresse est déjà utilisée dans l'annuaire."))
            if len(by_email.get(email, [])) > 1:
                row.errors.append(_("Adresse en double dans le fichier."))
        if values["date_arrivee"] and parse_date(values["date_arrivee"]) is None:
            row.errors.append(_("Date d'arrivée invalide (JJ/MM/AAAA)."))
        if values["contrat"] and values["contrat"].lower() not in CONTRACTS:
            row.errors.append(_("Contrat inconnu (CDI, CDD, Alternance ou Stage)."))
        manager = values["manager_email"].lower()
        if manager:
            if manager == email:
                row.errors.append(_("Une personne ne peut pas être son propre manager."))
            elif manager not in existing and manager not in by_email:
                row.errors.append(_("Manager introuvable dans l'annuaire ni dans le fichier."))
        if values["service"] and values["service"].lower() not in services:
            new_services.setdefault(values["service"].lower(), values["service"])
        if values["site"] and values["site"].lower() not in sites:
            new_sites.setdefault(values["site"].lower(), values["site"])
    return ImportPreview(rows, sorted(new_services.values()), sorted(new_sites.values()))


def rows_from_session(data: list) -> list[ImportRow]:
    return [ImportRow(line=r["line"], values=r["values"]) for r in data]


@transaction.atomic
def run(rows: list[ImportRow], *, actor, request=None) -> int:
    """Importe toutes les lignes ou aucune. Les contrôles sont refaits ici."""
    preview = check(rows_from_session([asdict(r) for r in rows]))
    if not preview.is_valid:
        raise ImportFileError(_("Des erreurs bloquantes restent : aucune ligne n'est importée."))
    services = {s.name.lower(): s for s in Service.objects.all()}
    sites = {s.name.lower(): s for s in Site.objects.all()}
    for name in preview.new_services:
        services[name.lower()] = Service.objects.create(name=name)
    for name in preview.new_sites:
        sites[name.lower()] = Site.objects.create(name=name)
    created = {}
    for row in preview.rows:
        v = row.values
        arrival = parse_date(v["date_arrivee"])
        employee = Employee.objects.create(
            first_name=v["prenom"],
            last_name=v["nom"],
            email=v["email"],
            job_title=v["poste"],
            service=services[v["service"].lower()],
            site=sites[v["site"].lower()],
            arrival_date=arrival,
            status=status_for_arrival(arrival),
            contract_type=CONTRACTS.get(v["contrat"].lower(), ""),
        )
        created[v["email"].lower()] = employee
        EmployeeChange.objects.create(
            employee=employee, actor=actor, kind=EmployeeChange.Kind.IMPORTED
        )
    existing = {
        e.email.lower(): e
        for e in Employee.objects.exclude(pk__in=[e.pk for e in created.values()])
    }
    for row in preview.rows:
        manager_email = row.values["manager_email"].lower()
        if manager_email:
            employee = created[row.values["email"].lower()]
            employee.manager = created.get(manager_email) or existing[manager_email]
            employee.save(update_fields=["manager", "updated_at"])
    audit.log(
        "people.imported",
        _("Import CSV : %(n)s fiches créées") % {"n": len(created)},
        actor=actor,
        request=request,
    )
    return len(created)
