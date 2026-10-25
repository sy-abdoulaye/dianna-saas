"""Guide de style /dev/styleguide/ : montre chaque composant dans ses états (lot 0).

Développement uniquement : la route n'est montée que si STYLEGUIDE_ENABLED, et chaque vue
renvoie 404 si DEBUG est faux. Les données affichées sont fictives (personnes du prototype).
"""

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core import undo
from apps.core.dev_forms import DemoFieldsForm, DemoFilterForm, DemoRequestForm
from apps.core.htmx import (
    Toast,
    after_action,
    confirm_response,
    error_response,
    form_error_response,
    is_htmx,
)
from apps.core.navigation import build_demo_nav
from apps.core.status import STATUSES


@dataclass(frozen=True)
class DemoPerson:
    first_name: str
    last_name: str
    job_title: str
    service: str
    site: str
    status: str = "active"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def email(self):
        import unicodedata

        def slug(value):
            value = unicodedata.normalize("NFD", value).encode("ascii", "ignore").decode()
            return value.lower().replace(" ", "")

        return f"{slug(self.first_name)}.{slug(self.last_name)}@exemple.fr"


PEOPLE = [
    DemoPerson("Camille", "Durand", "Conseillère support", "Support client", "Lyon"),
    DemoPerson("Mehdi", "Benali", "Développeur", "Produit et technique", "Paris"),
    DemoPerson("Thomas", "Roux", "Chargé de support", "Support client", "Lyon"),
    DemoPerson("Inès", "Garcia", "Cheffe de projet", "Produit et technique", "Paris"),
    DemoPerson("Louise", "Martin", "Responsable support", "Support client", "Lyon"),
    DemoPerson("Paul", "Lefèvre", "Directeur technique", "Produit et technique", "Paris"),
    DemoPerson("Sofia", "Nunes", "Comptable", "Finance", "Nantes", "upcoming"),
    DemoPerson("Antoine", "Bernard", "Technicien matériel", "Moyens généraux", "Lyon"),
    DemoPerson(
        "Hélène", "Faure", "Directrice des ressources humaines", "Ressources humaines", "Paris"
    ),
    DemoPerson("Marc", "Diallo", "Administrateur de la plateforme", "Moyens généraux", "Paris"),
    DemoPerson("Yasmine", "Kaci", "Chargée de recrutement", "Ressources humaines", "Paris"),
    DemoPerson("Julien", "Petit", "Commercial", "Ventes", "Nantes", "left"),
    DemoPerson("Nina", "Lambert", "Conseillère support", "Support client", "Lyon"),
    DemoPerson("Hugo", "Fabre", "Conseiller support", "Support client", "Lyon"),
    DemoPerson("Léa", "Fontaine", "Développeuse", "Produit et technique", "Paris"),
    DemoPerson("Karim", "Haddad", "Développeur", "Produit et technique", "Nantes"),
    DemoPerson("Claire", "Dubois", "Responsable ventes", "Ventes", "Nantes"),
    DemoPerson("Bastien", "Moreau", "Commercial", "Ventes", "Nantes"),
    DemoPerson("Amélie", "Chevalier", "Commerciale", "Ventes", "Paris"),
    DemoPerson("Romain", "Girard", "Comptable", "Finance", "Nantes"),
    DemoPerson("Élodie", "Vidal", "Responsable finance", "Finance", "Nantes"),
    DemoPerson("Samuel", "Perrin", "Analyste financier", "Finance", "Nantes"),
    DemoPerson("Chloé", "Renard", "Designer produit", "Produit et technique", "Paris"),
    DemoPerson("Pierre", "Blanc", "Conseiller support", "Support client", "Lyon"),
]

TEMPLATE = "core/styleguide.html"

ERROR_PAGES = {
    "403": ("pages/403.html", "403 · Accès non autorisé"),
    "404": ("pages/404.html", "404 · Page introuvable"),
    "500": ("pages/500.html", "500 · Erreur du serveur"),
    "module-desactive": ("pages/module_disabled.html", "Module désactivé"),
}


def _guard():
    if not settings.DEBUG:
        raise Http404


def _filtered_people(params):
    form = DemoFilterForm(params)
    form.is_valid()
    data = getattr(form, "cleaned_data", {})
    q = (data.get("q") or "").strip().lower()
    people = [
        p
        for p in PEOPLE
        if (not q or q in f"{p.full_name} {p.job_title} {p.service} {p.email}".lower())
        and (not data.get("service") or p.service == data["service"])
        and (not data.get("site") or p.site == data["site"])
    ]
    page_obj = Paginator(people, 8).get_page(params.get("page"))
    return form, page_obj


@login_not_required
@require_GET
def styleguide(request):
    _guard()
    filter_form, page_obj = _filtered_people(request.GET)
    results_url = reverse("dev:styleguide")
    if is_htmx(request) and request.htmx.target == "results":
        return render(
            request, f"{TEMPLATE}#results", {"page_obj": page_obj, "results_url": results_url}
        )

    invalid_form = DemoFieldsForm(data={"first_name": "", "email": "camille@", "note": "court"})
    invalid_form.is_valid()
    context = {
        "nav_groups": build_demo_nav(
            current="telework", counts={"telework": 2, "summer_leave": 1, "interventions": 1}
        ),
        "me": PEOPLE[0],
        "statuses": STATUSES,
        "fields_form": DemoFieldsForm(),
        "invalid_form": invalid_form,
        "filter_form": filter_form,
        "page_obj": page_obj,
        "results_url": results_url,
        "columns": [
            {"label": _("Collaborateur")},
            {"label": _("Service")},
            {"label": _("Site")},
            {"label": _("E-mail")},
            {"label": _("Statut")},
        ],
        "tabs": [
            {"label": _("Mes demandes"), "url": "#tabs", "active": True},
            {"label": _("À valider"), "url": "#tabs", "count": 2},
            {"label": _("Mon équipe"), "url": "#tabs"},
        ],
        "steps": [
            {"label": _("Auto-évaluation"), "state": "done"},
            {"label": _("Évaluation du manager"), "state": "current"},
            {"label": _("Entretien"), "state": "todo"},
            {"label": _("Signatures"), "state": "todo"},
        ],
        "view_options": [("list", _("Liste"), "list"), ("cards", _("Cartes"), "grid")],
        "toc": [
            ("colors", _("Couleurs")),
            ("type", _("Typographie")),
            ("buttons", _("Boutons")),
            ("badges", _("Badges")),
            ("fields", _("Champs")),
            ("banners", _("Bandeaux")),
            ("kpis", _("Indicateurs")),
            ("tabs", _("Onglets")),
            ("table", _("Tableau")),
            ("states", _("États vides")),
            ("stepper", _("Étapes")),
            ("modals", _("Modales")),
            ("toasts-demo", _("Notifications")),
            ("pages", _("Pages d'erreur")),
        ],
        "error_pages": [(slug, label) for slug, (_tpl, label) in ERROR_PAGES.items()],
    }
    return render(request, TEMPLATE, context)


@login_not_required
@require_http_methods(["GET", "POST"])
def demo_modal(request):
    """Modale de demande : 422 avec erreurs, ou succès avec notification et « Annuler »."""
    _guard()
    template = "core/partials/demo_request_modal.html"
    if request.method == "GET":
        return render(request, template, {"form": DemoRequestForm()})
    form = DemoRequestForm(request.POST)
    if not form.is_valid():
        return form_error_response(request, template, {"form": form})
    token = undo.make_token(request, "demo.request", form.cleaned_data["day"].isoformat())
    return after_action(
        request,
        Toast(
            title=_("Demande envoyée"),
            message=_("Votre demande a été transmise à Louise Martin."),
            emphasis="Louise Martin",
            action_label=_("Voir la demande"),
            action_url="#tabs",
            undo_url=reverse("dev:undo", args=[token]),
        ),
        close_modal=True,
    )


@login_not_required
@require_http_methods(["GET", "POST"])
def demo_confirm(request):
    _guard()
    danger = request.GET.get("danger") == "1"
    if request.method == "POST":
        if danger:
            toast = Toast(
                title=_("Fiche archivée"),
                message=_("Julien Petit est archivé."),
                emphasis="Julien Petit",
            )
        else:
            toast = Toast(title=_("Entretien marqué comme réalisé"))
        return after_action(request, toast, close_modal=True)
    context = {
        "danger": danger,
        "action_url": request.get_full_path(),
        "title": _("Archiver la fiche ?") if danger else _("Marquer l'entretien comme réalisé ?"),
        "text": _(
            "Julien Petit disparaîtra de l'annuaire et son compte sera désactivé. "
            "Ses données sont conservées."
        )
        if danger
        else _("Le salarié et vous pourrez ensuite signer l'entretien."),
        "ok_label": _("Archiver") if danger else _("Marquer comme réalisé"),
        "ok_icon": "trash" if danger else "check",
    }
    return confirm_response(request, **context)


@login_not_required
@require_POST
def demo_undo(request, token):
    _guard()
    try:
        undo.read_token(request, token)
    except undo.UndoError as exc:
        return error_response(exc)
    return after_action(
        request,
        Toast(title=_("Action annulée"), message=_("La demande a été retirée."), kind="info"),
    )


@login_not_required
@require_POST
def demo_toast(request):
    _guard()
    kind = request.POST.get("kind", "ok")
    titles = {
        "ok": (_("Compte rendu validé"), _("Camille Durand a été notifiée.")),
        "info": (_("Brouillon enregistré"), _("Vous pourrez le compléter plus tard.")),
        "warn": (_("Conflit d'absence"), _("2 personnes du service sont déjà absentes.")),
        "err": (_("Envoi impossible"), _("Corrigez les informations signalées.")),
    }
    title, message = titles.get(kind, titles["ok"])
    return after_action(
        request, Toast(title=title, message=message, kind=kind if kind in titles else "ok")
    )


@login_not_required
@require_POST
def demo_server_error(request):
    """Simule une erreur 500 pour montrer le bandeau « Le serveur n'a pas répondu »."""
    _guard()
    return HttpResponse(status=500)


@login_not_required
@require_GET
def demo_page(request, slug):
    _guard()
    if slug not in ERROR_PAGES:
        raise Http404
    template, _label = ERROR_PAGES[slug]
    return render(request, template)
