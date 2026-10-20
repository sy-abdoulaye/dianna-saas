"""Charge l'entreprise de démonstration « Exemple SAS » et l'entreprise « Autre SA »
(docs/07-donnees-de-demo.md). Développement uniquement : refusé si DEBUG est faux.

    python manage.py seed_demo [--reset]

Les personnes reprennent docs/reference/prototype-donnees-demo.js. Les dates sont recalculées
par rapport au jour du chargement (le prototype est figé au lundi 19 octobre 2026). Les données
des lots suivants (demandes, matériel, annonces…) sont ajoutées avec leurs modules.
"""

import unicodedata
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core import audit
from apps.core.models import Company, CompanyModule, Module, Service, Site
from apps.core.tenancy import tenant_context
from apps.people.models import ContractType, Employee, EmployeeStatus, Role, WorkTime

PASSWORD = "demo-dianna-2026"  # noqa: S105 (démonstration, refusé si DEBUG est faux)
PROTOTYPE_TODAY = date(2026, 10, 19)

SERVICES = [
    "Support client",
    "Produit et technique",
    "Finance",
    "Moyens généraux",
    "Ressources humaines",
    "Ventes",
]
SITES = ["Lyon", "Paris", "Nantes"]
ROLES = {"employe": Role.EMPLOYEE, "mgr": Role.MANAGER, "rh": Role.HR, "admin": Role.ADMIN}
STATUSES = {
    "actif": EmployeeStatus.ACTIVE,
    "arrivee": EmployeeStatus.UPCOMING,
    "parti": EmployeeStatus.LEFT,
}

# prénom, nom, poste, service, site, manager (pN), profil, statut, arrivée, contrat
PEOPLE = [
    (
        "Camille",
        "Durand",
        "Conseillère support",
        "Support client",
        "Lyon",
        "p5",
        "employe",
        "actif",
        "2022-03-14",
        "CDI",
    ),
    (
        "Mehdi",
        "Benali",
        "Développeur",
        "Produit et technique",
        "Paris",
        "p6",
        "employe",
        "actif",
        "2023-09-04",
        "CDI",
    ),
    (
        "Thomas",
        "Roux",
        "Chargé de support",
        "Support client",
        "Lyon",
        "p5",
        "employe",
        "actif",
        "2021-01-18",
        "CDI",
    ),
    (
        "Inès",
        "Garcia",
        "Cheffe de projet",
        "Produit et technique",
        "Paris",
        "p6",
        "employe",
        "actif",
        "2020-06-01",
        "CDI",
    ),
    (
        "Louise",
        "Martin",
        "Responsable support",
        "Support client",
        "Lyon",
        "p9",
        "mgr",
        "actif",
        "2019-02-11",
        "CDI",
    ),
    (
        "Paul",
        "Lefèvre",
        "Directeur technique",
        "Produit et technique",
        "Paris",
        "p9",
        "mgr",
        "actif",
        "2018-05-07",
        "CDI",
    ),
    (
        "Sofia",
        "Nunes",
        "Comptable",
        "Finance",
        "Nantes",
        "p21",
        "employe",
        "arrivee",
        "2026-11-03",
        "CDI",
    ),
    (
        "Antoine",
        "Bernard",
        "Technicien matériel",
        "Moyens généraux",
        "Lyon",
        "p9",
        "employe",
        "actif",
        "2022-10-03",
        "CDI",
    ),
    (
        "Hélène",
        "Faure",
        "Directrice des ressources humaines",
        "Ressources humaines",
        "Paris",
        "",
        "rh",
        "actif",
        "2017-09-01",
        "CDI",
    ),
    (
        "Marc",
        "Diallo",
        "Administrateur de la plateforme",
        "Moyens généraux",
        "Paris",
        "p9",
        "admin",
        "actif",
        "2021-04-12",
        "CDI",
    ),
    (
        "Yasmine",
        "Kaci",
        "Chargée de recrutement",
        "Ressources humaines",
        "Paris",
        "p9",
        "rh",
        "actif",
        "2024-01-08",
        "CDI",
    ),
    (
        "Julien",
        "Petit",
        "Commercial",
        "Ventes",
        "Nantes",
        "p17",
        "employe",
        "parti",
        "2020-11-02",
        "CDI",
    ),
    (
        "Nina",
        "Lambert",
        "Conseillère support",
        "Support client",
        "Lyon",
        "p5",
        "employe",
        "actif",
        "2023-03-20",
        "CDD",
    ),
    (
        "Hugo",
        "Fabre",
        "Conseiller support",
        "Support client",
        "Lyon",
        "p5",
        "employe",
        "actif",
        "2024-05-06",
        "CDI",
    ),
    (
        "Léa",
        "Fontaine",
        "Développeuse",
        "Produit et technique",
        "Paris",
        "p6",
        "employe",
        "actif",
        "2022-01-24",
        "CDI",
    ),
    (
        "Karim",
        "Haddad",
        "Développeur",
        "Produit et technique",
        "Nantes",
        "p6",
        "employe",
        "actif",
        "2021-09-13",
        "CDI",
    ),
    (
        "Claire",
        "Dubois",
        "Responsable ventes",
        "Ventes",
        "Nantes",
        "p9",
        "mgr",
        "actif",
        "2019-10-14",
        "CDI",
    ),
    (
        "Bastien",
        "Moreau",
        "Commercial",
        "Ventes",
        "Nantes",
        "p17",
        "employe",
        "actif",
        "2023-02-27",
        "CDI",
    ),
    (
        "Amélie",
        "Chevalier",
        "Commerciale",
        "Ventes",
        "Paris",
        "p17",
        "employe",
        "actif",
        "2022-08-29",
        "CDI",
    ),
    (
        "Romain",
        "Girard",
        "Comptable",
        "Finance",
        "Nantes",
        "p21",
        "employe",
        "actif",
        "2020-03-02",
        "CDI",
    ),
    (
        "Élodie",
        "Vidal",
        "Responsable finance",
        "Finance",
        "Nantes",
        "p9",
        "mgr",
        "actif",
        "2018-11-19",
        "CDI",
    ),
    (
        "Samuel",
        "Perrin",
        "Analyste financier",
        "Finance",
        "Nantes",
        "p21",
        "employe",
        "actif",
        "2024-09-02",
        "CDI",
    ),
    (
        "Chloé",
        "Renard",
        "Designer produit",
        "Produit et technique",
        "Paris",
        "p6",
        "employe",
        "actif",
        "2023-06-12",
        "CDI",
    ),
    (
        "Pierre",
        "Blanc",
        "Conseiller support",
        "Support client",
        "Lyon",
        "p5",
        "employe",
        "actif",
        "2025-02-03",
        "CDI",
    ),
]
# Comptes de démonstration (docs/07-donnees-de-demo.md) : salarié, manager, RH, admin.
DEMO_ACCOUNTS = {"p1", "p5", "p9", "p10"}

OTHER_COMPANY = [
    ("Nadia", "Berger", "Directrice générale", "Direction", "Bordeaux", "", "admin"),
    ("Lucas", "Morel", "Responsable logistique", "Logistique", "Bordeaux", "o1", "mgr"),
    ("Emma", "Rousseau", "Préparatrice de commandes", "Logistique", "Bordeaux", "o2", "employe"),
    ("Hugo", "Lemaire", "Cariste", "Logistique", "Bordeaux", "o2", "employe"),
]
OTHER_ACCOUNTS = {"o1": "nadia.berger@autre.fr"}


def slug(value: str) -> str:
    value = unicodedata.normalize("NFD", value).encode("ascii", "ignore").decode()
    return "".join(c for c in value.lower() if c.isalpha())


def shifted(iso: str) -> date:
    """Décale une date du prototype pour garder le même écart avec aujourd'hui."""
    return date.fromisoformat(iso) + (timezone.localdate() - PROTOTYPE_TODAY)


class Command(BaseCommand):
    help = "Charge les entreprises de démonstration Exemple SAS et Autre SA."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Supprime puis recharge.")

    def handle(self, *args, reset=False, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo est réservé au développement (DEBUG = True).")
        existing = Company.objects.filter(slug__in=["exemple", "autre"])
        if existing.exists():
            if not reset:
                raise CommandError("Les données de démonstration existent déjà : --reset.")
            self._reset(existing)
        with transaction.atomic():
            self._seed_exemple()
            self._seed_autre()
        base = f"{settings.SITE_SCHEME}://exemple.{settings.BASE_DOMAIN}"
        port = f":{settings.SITE_PORT}" if settings.SITE_PORT else ""
        self.stdout.write(self.style.SUCCESS("Données de démonstration chargées."))
        self.stdout.write(f"Connexion : {base}{port}/connexion/ (mot de passe : {PASSWORD})")

    def _reset(self, companies):
        emails = []
        for company in companies:
            emails += list(
                Employee.all_companies.filter(company=company, user__isnull=False).values_list(
                    "user__email", flat=True
                )
            )
        companies.delete()
        User.objects.filter(email__in=emails).delete()

    def _company(self, name, slug_, services, sites):
        company = Company.objects.create(name=name, slug=slug_)
        CompanyModule.all_companies.bulk_create(
            [CompanyModule(company=company, module=m) for m in Module.values]
        )
        with tenant_context(company):
            services = {n: Service.objects.create(name=n) for n in services}
            sites = {n: Site.objects.create(name=n) for n in sites}
        return company, services, sites

    def _user(self, email):
        return User.objects.create_user(email, PASSWORD)

    def _seed_exemple(self):
        company, services, sites = self._company("Exemple SAS", "exemple", SERVICES, SITES)
        with tenant_context(company):
            people = {}
            for index, row in enumerate(PEOPLE, start=1):
                first, last, job, service, site, _m, role, status, arrival, contract = row
                key = f"p{index}"
                email = f"{slug(first)}.{slug(last)}@exemple.fr"
                people[key] = Employee.objects.create(
                    first_name=first,
                    last_name=last,
                    email=email,
                    job_title=job,
                    service=services[service],
                    site=sites[site],
                    role=ROLES[role],
                    status=STATUSES[status],
                    arrival_date=shifted(arrival)
                    if status == "arrivee"
                    else date.fromisoformat(arrival),
                    departure_date=timezone.localdate() - timedelta(days=30)
                    if status == "parti"
                    else None,
                    contract_type=ContractType.CDD if contract == "CDD" else ContractType.CDI,
                    work_time=WorkTime.FULL_35,
                    # Comme le prototype : téléphone, bureau, matricule.
                    phone=f"04 72 00 00 {9 + index:02d}",
                    office=f"Étage {1 + (index - 1) % 4}, B-{9 + index}",
                    registration_number=f"{210 + (index - 1) * 7:05d}",
                    user=self._user(email) if key in DEMO_ACCOUNTS else None,
                )
            for index, row in enumerate(PEOPLE, start=1):
                manager_key = row[5]
                if manager_key:
                    employee = people[f"p{index}"]
                    employee.manager = people[manager_key]
                    employee.save(update_fields=["manager", "updated_at"])
            # Historique et journal : création des fiches et une modification par les RH.
            from apps.people.models import EmployeeChange

            helene = people["p9"]
            for employee in people.values():
                EmployeeChange.objects.create(employee=employee, actor=helene, kind="created")
            EmployeeChange.objects.create(
                employee=people["p1"], actor=helene, kind="updated", fields=["office", "phone"]
            )
            self._seed_requests(people)
            audit.log("platform.demo_loaded", "Données de démonstration chargées")

    def _seed_requests(self, people):
        """Demandes du prototype (prototype-donnees-demo.js, seedRequests), dates recalculées
        par rapport au lundi de la semaine du chargement. Écrites sans e-mail."""
        from apps.approvals import workflow
        from apps.approvals.models import (
            LeaveRequest,
            OnCallDeclaration,
            RequestEvent,
            SummerCampaign,
            TeleworkRequest,
        )
        from apps.core import notifications
        from apps.core.models import Notification

        today = timezone.localdate()
        monday = today - timedelta(days=today.weekday())
        campaign = SummerCampaign.objects.create(
            label="Été 2027",
            period_start=date(2027, 6, 1),
            period_end=date(2027, 9, 30),
            deadline=date(2027, 2, 28),
            status=SummerCampaign.Status.OPEN,
        )
        refused_reason = "Effectif insuffisant ce jour-là."
        counter = {"n": 0}

        def add(model, key, status, decided_by="p5", **data):
            counter["n"] += 1
            submitted = timezone.now() - timedelta(days=2 + counter["n"] % 9)
            requester = people[key]
            request = model.objects.create(
                requester=requester, submitted_at=submitted, status=status, **data
            )
            RequestEvent.objects.create(
                request_type=model.request_type,
                request_id=request.pk,
                actor=requester,
                action="submitted",
            )
            if status in ("approved", "refused"):
                request.decided_by = people[decided_by]
                request.decided_at = submitted + timedelta(days=1)
                request.decision_comment = refused_reason if status == "refused" else ""
                request.save()
                RequestEvent.objects.create(
                    request_type=model.request_type,
                    request_id=request.pk,
                    actor=people[decided_by],
                    action=status,
                    comment=request.decision_comment,
                )
            workflow.sync_calendar(request)
            if status == "pending":
                for validator in workflow.first_validators(request):
                    notifications.notify(
                        validator,
                        f"{requester.full_name} : {request._meta.verbose_name} à valider",
                        url=workflow._module_url(request, "a-valider"),
                        kind=Notification.Kind.REQUEST,
                    )
            return request

        def day(offset):
            return monday + timedelta(days=offset)

        tw = TeleworkRequest
        add(tw, "p1", "approved", date=day(2))
        add(tw, "p1", "pending", date=day(9), comment="Travaux dans l'immeuble")
        add(tw, "p3", "approved", date=day(1))
        add(tw, "p3", "approved", date=day(3))
        add(tw, "p13", "pending", date=day(4))
        add(tw, "p24", "refused", date=day(2), comment="Rendez-vous médical")
        add(tw, "p2", "approved", "p6", date=day(0))
        add(tw, "p4", "approved", "p6", date=day(4))
        add(tw, "p15", "approved", "p6", date=day(1))
        add(tw, "p14", "pending", date=day(8))
        lv = LeaveRequest
        summer = {"campaign": campaign, "leave_type": LeaveRequest.LeaveType.SUMMER}
        add(
            lv,
            "p1",
            "pending",
            start=date(2027, 8, 2),
            end=date(2027, 8, 13),
            comment="Deux semaines en famille",
            **summer,
        )
        add(lv, "p3", "approved", start=date(2027, 7, 19), end=date(2027, 7, 30), **summer)
        add(lv, "p13", "pending", start=date(2027, 8, 2), end=date(2027, 8, 20), **summer)
        add(lv, "p24", "approved", start=date(2027, 8, 9), end=date(2027, 8, 27), **summer)
        add(lv, "p14", "pending", start=date(2027, 7, 26), end=date(2027, 8, 6), **summer)
        add(lv, "p2", "approved", "p6", start=date(2027, 8, 2), end=date(2027, 8, 20), **summer)
        add(lv, "p4", "pending", start=date(2027, 7, 12), end=date(2027, 7, 23), **summer)
        add(lv, "p5", "approved", "p9", start=date(2027, 8, 16), end=date(2027, 8, 27), **summer)
        add(
            lv,
            "p14",
            "approved",
            start=day(7),
            end=day(11),
            leave_type=LeaveRequest.LeaveType.OTHER,
        )
        oc = OnCallDeclaration
        add(oc, "p3", "approved", start=day(4), end=day(6), description="Week-end d'astreinte")
        add(oc, "p24", "pending", start=day(11), end=day(13))
        add(
            oc,
            "p3",
            "approved",
            kind=OnCallDeclaration.Kind.INTERVENTION,
            start=day(-3),
            end=day(-3),
            hours=2.5,
            description="Incident serveur de messagerie",
        )
        add(oc, "p16", "pending", "p6", start=day(5), end=day(6))

    def _seed_autre(self):
        services = sorted({row[3] for row in OTHER_COMPANY})
        sites = sorted({row[4] for row in OTHER_COMPANY})
        company, services, sites = self._company("Autre SA", "autre", services, sites)
        with tenant_context(company):
            people = {}
            for index, (first, last, job, service, site, manager, role) in enumerate(
                OTHER_COMPANY, start=1
            ):
                key = f"o{index}"
                email = OTHER_ACCOUNTS.get(key) or f"{slug(first)}.{slug(last)}@autre.fr"
                people[key] = Employee.objects.create(
                    first_name=first,
                    last_name=last,
                    email=email,
                    job_title=job,
                    service=services[service],
                    site=sites[site],
                    role=ROLES[role],
                    manager=people.get(manager),
                    arrival_date=date(2022, 1, 3),
                    contract_type=ContractType.CDI,
                    user=self._user(email) if key in OTHER_ACCOUNTS else None,
                )
            audit.log("platform.demo_loaded", "Données de démonstration chargées")
