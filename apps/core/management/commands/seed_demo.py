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


# Répondants du questionnaire « Intégration » du prototype : arrivés depuis moins d'un an à
# la date du chargement, pour que le public « Arrivés depuis moins d'un an » compte au moins
# 3 personnes (seuil d'anonymat, L6-05). Écart au prototype, figé en 2024 et 2025.
NEW_HIRES = {
    key: timezone.localdate() - timedelta(days=days)
    for key, days in (("p14", 300), ("p22", 200), ("p24", 120))
}


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
                    else NEW_HIRES.get(key) or date.fromisoformat(arrival),
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
            self._seed_closures(sites)
            self._seed_requests(people)
            self._seed_announcements(people)
            self._seed_surveys(people)
            audit.log("platform.demo_loaded", "Données de démonstration chargées")

    def _seed_closures(self, sites):
        """Fermeture du site de Lyon le 24 décembre (annonce du prototype), T-16."""
        from apps.agenda.models import Closure

        today = timezone.localdate()
        christmas_eve = date(today.year, 12, 24)
        if christmas_eve < today:
            christmas_eve = date(today.year + 1, 12, 24)
        Closure.objects.create(
            date=christmas_eve, label="Fermeture du site de Lyon", site=sites["Lyon"]
        )

    def _seed_requests(self, people):
        """Demandes du prototype (prototype-donnees-demo.js, seedRequests), dates recalculées
        par rapport au lundi de la semaine du chargement. Écrites sans e-mail."""
        from apps.approvals.models import SummerCampaign

        writer = DemoRequestWriter(people)
        campaign = SummerCampaign.objects.create(
            label="Été 2027",
            period_start=date(2027, 6, 1),
            period_end=date(2027, 9, 30),
            deadline=date(2027, 2, 28),
            status=SummerCampaign.Status.OPEN,
        )
        self._seed_telework(writer)
        self._seed_leave(writer, campaign)
        self._seed_on_call(writer)
        self._seed_transport(writer)
        self._seed_equipment_requests(writer)
        self._seed_equipment(people)

    def _seed_telework(self, writer):
        from apps.approvals.models import TeleworkRequest

        day = writer.day
        writer.add(TeleworkRequest, "p1", "approved", date=day(2))
        writer.add(TeleworkRequest, "p1", "pending", date=day(9), comment="Travaux dans l'immeuble")
        writer.add(TeleworkRequest, "p3", "approved", date=day(1))
        writer.add(TeleworkRequest, "p3", "approved", date=day(3))
        writer.add(TeleworkRequest, "p13", "pending", date=day(4))
        writer.add(TeleworkRequest, "p24", "refused", date=day(2), comment="Rendez-vous médical")
        writer.add(TeleworkRequest, "p2", "approved", "p6", date=day(0))
        writer.add(TeleworkRequest, "p4", "approved", "p6", date=day(4))
        writer.add(TeleworkRequest, "p15", "approved", "p6", date=day(1))
        writer.add(TeleworkRequest, "p14", "pending", date=day(8))

    def _seed_leave(self, writer, campaign):
        from apps.approvals.models import LeaveRequest

        summer = {"campaign": campaign, "leave_type": LeaveRequest.LeaveType.SUMMER}
        writer.add(
            LeaveRequest,
            "p1",
            "pending",
            start=date(2027, 8, 2),
            end=date(2027, 8, 13),
            comment="Deux semaines en famille",
            **summer,
        )
        writer.add(
            LeaveRequest, "p3", "approved", start=date(2027, 7, 19), end=date(2027, 7, 30), **summer
        )
        writer.add(
            LeaveRequest, "p13", "pending", start=date(2027, 8, 2), end=date(2027, 8, 20), **summer
        )
        writer.add(
            LeaveRequest, "p24", "approved", start=date(2027, 8, 9), end=date(2027, 8, 27), **summer
        )
        writer.add(
            LeaveRequest, "p14", "pending", start=date(2027, 7, 26), end=date(2027, 8, 6), **summer
        )
        writer.add(
            LeaveRequest,
            "p2",
            "approved",
            "p6",
            start=date(2027, 8, 2),
            end=date(2027, 8, 20),
            **summer,
        )
        writer.add(
            LeaveRequest, "p4", "pending", start=date(2027, 7, 12), end=date(2027, 7, 23), **summer
        )
        writer.add(
            LeaveRequest,
            "p5",
            "approved",
            "p9",
            start=date(2027, 8, 16),
            end=date(2027, 8, 27),
            **summer,
        )
        writer.add(
            LeaveRequest,
            "p14",
            "approved",
            start=writer.day(7),
            end=writer.day(11),
            leave_type=LeaveRequest.LeaveType.OTHER,
        )

    def _seed_on_call(self, writer):
        from apps.approvals.models import OnCallDeclaration

        day = writer.day
        writer.add(
            OnCallDeclaration,
            "p3",
            "approved",
            start=day(4),
            end=day(6),
            description="Week-end d'astreinte",
        )
        writer.add(OnCallDeclaration, "p24", "pending", start=day(11), end=day(13))
        writer.add(
            OnCallDeclaration,
            "p3",
            "approved",
            kind=OnCallDeclaration.Kind.INTERVENTION,
            start=day(-3),
            end=day(-3),
            hours=2.5,
            description="Incident serveur de messagerie",
        )
        writer.add(OnCallDeclaration, "p16", "pending", "p6", start=day(5), end=day(6))

    def _seed_transport(self, writer):
        """Transport (prototype : seedRequests), mois en cours et mois précédent."""
        from apps.approvals.models import TransportProof

        this_month = writer.today.replace(day=1)
        last_month = (this_month - timedelta(days=1)).replace(day=1)
        pdf, jpg = demo_pdf(), demo_jpg()
        monthly = {"ticket_type": TransportProof.TicketType.MONTHLY, "amount": "84.10"}
        writer.add(
            TransportProof,
            "p1",
            "approved",
            "p9",
            month=last_month,
            **monthly,
            **demo_proof("abonnement-septembre.pdf", pdf, "application/pdf"),
        )
        writer.add(
            TransportProof,
            "p1",
            "pending",
            month=this_month,
            **monthly,
            **demo_proof("abonnement-octobre.pdf", pdf, "application/pdf"),
        )
        writer.add(
            TransportProof,
            "p3",
            "pending",
            month=this_month,
            **monthly,
            **demo_proof("justificatif-tcl.pdf", pdf, "application/pdf"),
        )
        writer.add(
            TransportProof,
            "p2",
            "refused",
            "p9",
            month=last_month,
            ticket_type=TransportProof.TicketType.SINGLE,
            amount="12.40",
            **demo_proof("ticket.jpg", jpg, "image/jpeg"),
        )
        writer.add(
            TransportProof,
            "p15",
            "pending",
            month=this_month,
            ticket_type=TransportProof.TicketType.MONTHLY,
            amount="86.40",
            **demo_proof("navigo-oct.pdf", pdf, "application/pdf"),
        )

    def _seed_equipment_requests(self, writer):
        """Matériel : demandes (prototype : seedRequests)."""
        from apps.equipment.models import EquipmentRequest

        writer.add(
            EquipmentRequest,
            "p1",
            "pending",
            kind="headset",
            reason="Casque actuel défectueux (micro)",
        )
        writer.add(
            EquipmentRequest,
            "p13",
            "approved",
            "p9",
            kind="screen",
            reason="Deuxième écran pour le suivi des tickets",
        )
        writer.add(
            EquipmentRequest, "p2", "pending", kind="laptop", reason="Renouvellement (4 ans)"
        )

    def _seed_announcements(self, people):
        """Annonces du prototype (seedAnnonces), datées par rapport au jour du chargement.
        Écart : « Nouvelle politique de télétravail » ne mentionne pas de délai (M-01)."""
        from apps.announcements.models import Announcement, AnnouncementRead

        now = timezone.now()
        for title, category, body, author, days, pinned, readers in DEMO_ANNOUNCEMENTS:
            announcement = Announcement.objects.create(
                title=title,
                category=category,
                body=body,
                author=people[author],
                published_at=now - timedelta(days=days),
                pinned=pinned,
            )
            for key in {author, *readers}:
                AnnouncementRead.objects.create(announcement=announcement, employee=people[key])

    def _seed_surveys(self, people):
        """Questionnaires du prototype (seedQuestionnaires), écrits par les services : public
        figé à la publication, réponses anonymes sans lien avec les reçus. Écarts :
        « Intégration » n'a que 2 réponses (résultats masqués) ; le brouillon a une question
        notée, obligatoire dans le formulaire."""
        from apps.surveys import services
        from apps.surveys.models import Survey

        hr, today = people["p9"], timezone.localdate()
        rng = DemoRandom(7)
        for spec in DEMO_SURVEYS:
            survey = services.create_draft(
                services.DraftData(spec["title"], spec["audience"], None, *spec["questions"]),
                actor=hr,
            )
            if spec["status"] == "draft":
                continue
            services.publish(survey, actor=hr)
            respondents = [people[key] for key in spec["respondents"]]
            rng.shuffle(respondents)
            for person in respondents:
                services.submit_answers(survey, person, demo_answers(survey, rng))
            if spec["status"] == "closed":
                services.close(survey, actor=hr)
            # Dates d'affichage du prototype (échéance, publication), relatives à aujourd'hui.
            Survey.objects.filter(pk=survey.pk).update(
                due_date=today + timedelta(days=spec["due_in"]),
                published_at=timezone.now() + timedelta(days=spec["due_in"] - 30),
            )

    def _seed_equipment(self, people):
        """Parc du prototype (seedEquipment) : 15 équipements, attributions et historique."""
        from apps.equipment.models import (
            EquipmentAssignment,
            EquipmentEvent,
            EquipmentItem,
        )

        rows = [
            ("laptop", "Dell Latitude 5440", "p1", "assigned"),
            ("screen", 'Dell U2723QE 27"', "p1", "assigned"),
            ("laptop", "Dell Latitude 5440", "p3", "assigned"),
            ("headset", "Jabra Evolve2 55", "p3", "assigned"),
            ("laptop", 'MacBook Pro 14"', "p2", "assigned"),
            ("laptop", 'MacBook Pro 14"', "p4", "assigned"),
            ("laptop", "Dell Latitude 5440", "p5", "assigned"),
            ("phone", "iPhone 14", "p5", "assigned"),
            ("screen", 'Dell U2723QE 27"', "p13", "assigned"),
            ("laptop", "Dell Latitude 5440", "p13", "assigned"),
            ("laptop", "Dell Latitude 5440", None, "in_stock"),
            ("screen", 'Dell U2723QE 27"', None, "in_stock"),
            ("headset", "Jabra Evolve2 55", None, "in_stock"),
            ("laptop", "Lenovo ThinkPad T14", None, "repair"),
            ("phone", "iPhone 13", None, "in_stock"),
        ]
        hr = people["p9"]
        for index, (kind, model, key, status) in enumerate(rows):
            holder = people[key] if key else None
            since = timezone.now() - timedelta(days=40 + index * 23)
            item = EquipmentItem.objects.create(
                kind=kind,
                model=model,
                serial_number=f"DN-{1040 + index * 13:05d}",
                status=status,
                holder=holder,
                assigned_at=since if holder else None,
            )
            EquipmentEvent.objects.create(item=item, action="added", actor=hr)
            if holder:
                EquipmentAssignment.objects.create(
                    item=item, employee=holder, assigned_at=since, assigned_by=hr
                )
                EquipmentEvent.objects.create(
                    item=item, action="assigned", actor=hr, employee=holder
                )
            if status == "repair":
                EquipmentEvent.objects.create(item=item, action="repair", actor=hr)

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


def demo_pdf() -> bytes:
    """Petit PDF valide (justificatifs de démonstration)."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )


def demo_jpg() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (320, 200), (236, 239, 244)).save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


REFUSED_REASON = "Effectif insuffisant ce jour-là."


class DemoRequestWriter:
    """Écrit une demande de démonstration comme le moteur commun : contrôles du service,
    événements, décision, calendrier et notification des valideurs, sans e-mail."""

    def __init__(self, people):
        self.people = people
        self.today = timezone.localdate()
        self.monday = self.today - timedelta(days=self.today.weekday())
        self.count = 0

    def day(self, offset: int) -> date:
        return self.monday + timedelta(days=offset)

    def add(self, model, key, status, decided_by="p5", **data):
        from apps.approvals import workflow

        self.count += 1
        submitted = timezone.now() - timedelta(days=2 + self.count % 9)
        requester = self.people[key]
        request = model(
            requester=requester,
            submitted_at=submitted,
            status=status,
            **self._shift_telework_day(model, requester, data),
        )
        self._check(request, status, data)
        request.save()
        self._event(request, requester, "submitted")
        if status in ("approved", "refused"):
            self._decide(request, status, self.people[decided_by], submitted)
        workflow.sync_calendar(request)
        if status == "pending":
            self._notify_validators(request)
        return request

    def _shift_telework_day(self, model, requester, data: dict) -> dict:
        """Jour férié ou fermé (selon la date du chargement) : jour ouvré suivant."""
        from apps.agenda.days import day_off
        from apps.approvals.models import TeleworkRequest

        if model is TeleworkRequest:
            while data["date"].weekday() >= 5 or day_off(data["date"], requester.site_id):
                data["date"] += timedelta(days=1)
        return data

    def _check(self, request, status, data: dict) -> None:
        """Contrôles métier du service (A3-02), sauf pour une demande déjà passée : ses dates
        sont antérieures à aujourd'hui (seule exception, CLAUDE.md)."""
        from apps.approvals import workflow
        from apps.approvals.models import ACTIVE_STATUSES, TransportProof

        if isinstance(request, TransportProof):
            request.compute_validity()
        last_day = (
            getattr(request, "end", None)
            or getattr(request, "date", None)
            or getattr(request, "valid_until", None)
            or self.today
        )
        if status in ACTIVE_STATUSES and last_day >= self.today:
            errors = workflow.check_request(request, campaign=data.get("campaign"))
            if errors:
                raise CommandError(f"Demande de démonstration invalide : {errors}")

    def _event(self, request, actor, action, comment=""):
        from apps.approvals.models import RequestEvent

        RequestEvent.objects.create(
            request_type=request.request_type,
            request_id=request.pk,
            actor=actor,
            action=action,
            comment=comment,
        )

    def _decide(self, request, status, decided_by, submitted) -> None:
        request.decided_by = decided_by
        request.decided_at = submitted + timedelta(days=1)
        request.decision_comment = REFUSED_REASON if status == "refused" else ""
        request.save()
        self._event(request, decided_by, status, request.decision_comment)

    def _notify_validators(self, request) -> None:
        from apps.approvals import workflow
        from apps.core import notifications
        from apps.core.models import Notification

        for validator in workflow.first_validators(request):
            notifications.notify(
                validator,
                f"{request.requester.full_name} : {request._meta.verbose_name} à valider",
                url=workflow._module_url(request, "a-valider"),
                kind=Notification.Kind.REQUEST,
                source=request,
            )


def demo_proof(name: str, data: bytes, mime: str) -> dict:
    from django.core.files.base import ContentFile

    return {
        "file": ContentFile(data, name=f"justificatif.{name.rsplit('.', 1)[1]}"),
        "file_type": mime,
        "original_name": name,
    }


DEMO_ANNOUNCEMENTS = [
    (
        "Fermeture du site de Lyon le 24 décembre",
        "site_life",
        "Le site de Lyon sera fermé le jeudi 24 décembre. Les équipes support passent en "
        "astreinte renforcée. Merci de poser vos congés avant le 20 novembre.",
        "p9",
        2,
        True,
        ["p3"],
    ),
    (
        "Campagne des entretiens individuels 2026",
        "hr",
        "La campagne est ouverte du 5 octobre au 18 décembre. Chaque salarié complète son "
        "auto-évaluation, puis son manager planifie l'entretien.",
        "p9",
        7,
        True,
        ["p1", "p3", "p5"],
    ),
    (
        "Nouvelle politique de télétravail",
        "company",
        "Deux jours de télétravail par semaine, à déclarer dans Dianna. Les demandes sont "
        "validées par le manager.",
        "p9",
        15,
        False,
        ["p1", "p5"],
    ),
    (
        "Rappel : exercice d'évacuation à Paris",
        "safety",
        "Un exercice d'évacuation aura lieu le jeudi 5 novembre à 10 h. Le point de "
        "rassemblement est devant l'entrée principale.",
        "p10",
        21,
        False,
        ["p1"],
    ),
    (
        "Bienvenue à Sofia Nunes",
        "company",
        "Sofia rejoindra l'équipe finance à Nantes le 3 novembre en tant que comptable.",
        "p9",
        3,
        False,
        [],
    ),
]

SURVEY_RESPONDENTS = [
    "p2", "p3", "p4", "p6", "p8", "p11", "p13", "p14", "p15",
    "p16", "p18", "p19", "p20", "p22", "p23", "p24", "p17", "p21",
]  # fmt: skip

DEMO_SURVEYS = [
    {
        "title": "Baromètre de qualité de vie au travail 2026",
        "audience": "all",
        "status": "open",
        "due_in": 25,
        "questions": (
            [
                "Je me sens bien dans mon équipe.",
                "Ma charge de travail est soutenable.",
                "Je dispose des outils nécessaires pour travailler.",
            ],
            "Qu'est-ce qui pourrait améliorer votre quotidien ?",
        ),
        "respondents": SURVEY_RESPONDENTS[:14],
    },
    {
        "title": "Retour sur l'intégration des nouveaux arrivants",
        "audience": "new_hires",
        "status": "open",
        "due_in": 42,
        "questions": (
            ["Mon accueil s'est bien passé.", "Je comprends mes objectifs."],
            "Un point à améliorer dans l'intégration ?",
        ),
        "respondents": ["p24", "p22"],
    },
    {
        "title": "Enquête télétravail 2025",
        "audience": "all",
        "status": "closed",
        "due_in": -311,
        "questions": (
            [
                "Le télétravail m'aide à mieux organiser ma semaine.",
                "Je reste en contact avec mon équipe.",
            ],
            "",
        ),
        "respondents": SURVEY_RESPONDENTS,
    },
    {
        "title": "Besoins de formation 2027",
        "audience": "all",
        "status": "draft",
        "due_in": 0,
        "questions": (
            ["Les formations proposées répondent à mes besoins."],
            "Quelle formation vous aiderait le plus en 2027 ?",
        ),
        "respondents": [],
    },
]

DEMO_COMMENTS = {
    2: [
        "Les pics de charge reviennent chaque fin de mois.",
        "Peu d'échanges avec les autres équipes.",
    ],
    3: ["Correct, mais les outils sont parfois lents.", "Ça dépend des semaines."],
    4: ["Bonne entente, réunions utiles.", "Le télétravail aide beaucoup."],
    5: ["Très bonne ambiance dans l'équipe.", "Matériel récent et adapté."],
}


class DemoRandom:
    """Générateur reproductible du prototype (congruence linéaire), sans `random` : les
    données de démonstration sont les mêmes à chaque chargement."""

    def __init__(self, seed: int):
        self.seed = seed

    def next(self) -> float:
        self.seed = (self.seed * 1103515245 + 12345) & 0x7FFFFFFF
        return self.seed / 0x7FFFFFFF

    def shuffle(self, items: list) -> None:
        for index in range(len(items) - 1, 0, -1):
            other = int(self.next() * (index + 1))
            items[index], items[other] = items[other], items[index]


def demo_answers(survey, rng: DemoRandom) -> dict:
    """Réponse du prototype : notes de 2 à 5, commentaire une fois sur trois environ."""
    from apps.surveys.models import Question

    raw = {}
    for question in survey.questions.all():
        if question.kind == Question.Kind.SCALE:
            score = 2 + int(rng.next() * 4)
            comment = DEMO_COMMENTS[score][int(rng.next() * 2)] if rng.next() > 0.6 else ""
            raw[question.pk] = {"score": score, "comment": comment}
        else:
            text = "Plus de visibilité sur le planning de l'équipe." if rng.next() > 0.5 else ""
            raw[question.pk] = {"text": text}
    return raw
