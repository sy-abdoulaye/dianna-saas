from django.urls import path, register_converter

from apps.core.views import undo_action

from . import views

app_name = "approvals"

# Chemins visibles en français (L1-03) : le convertisseur n'accepte que ces trois préfixes et
# les traduit en type interne (telework, leave, on_call).
SLUGS = {
    "telework": "teletravail",
    "leave": "conges",
    "on_call": "astreintes",
    "transport": "transport",
    # Demandes de matériel (lot 5) : le moteur commun traite /materiel/<id>/valider/… ;
    # l'écran /materiel/ est celui de l'application Matériel (inclus avant celle-ci).
    "equipment": "materiel",
}


class KindConverter:
    regex = "|".join(SLUGS.values())

    def to_python(self, value):
        return {slug: kind for kind, slug in SLUGS.items()}[value]

    def to_url(self, value):
        return SLUGS[value]


register_converter(KindConverter, "kind")

urlpatterns = [
    path("demandes/annuler/<str:token>/", undo_action, {"prefix": "requests."}, name="undo"),
    path("conges/campagnes/", views.campaigns, name="campaigns"),
    path("conges/campagnes/nouvelle/", views.new_campaign, name="new_campaign"),
    path("conges/campagnes/<int:pk>/synthese/", views.campaign_summary, name="campaign_summary"),
    path("conges/campagnes/<int:pk>/<str:action>/", views.campaign_status, name="campaign_status"),
    # Entrées du menu (noms utilisés par apps.core.navigation).
    path("teletravail/", views.request_list, {"kind": "telework"}, name="telework"),
    path("conges/", views.request_list, {"kind": "leave"}, name="leave"),
    path("astreintes/", views.request_list, {"kind": "on_call"}, name="on_call"),
    path("transport/", views.request_list, {"kind": "transport"}, name="transport"),
    # Justificatif : servi après contrôle de la permission, jamais par lien signé (L5-01).
    path("transport/<uuid:public_id>/justificatif/", views.proof_file, name="proof_file"),
    path("<kind:kind>/", views.request_list, name="list"),
    path("<kind:kind>/nouvelle/", views.new_request, name="new"),
    path("<kind:kind>/export/", views.export_requests, name="export"),
    path("<kind:kind>/<uuid:public_id>/", views.detail, name="detail"),
    path("<kind:kind>/<uuid:public_id>/valider/", views.approve, name="approve"),
    path("<kind:kind>/<uuid:public_id>/refuser/", views.refuse, name="refuse"),
    path("<kind:kind>/<uuid:public_id>/annuler/", views.cancel, name="cancel"),
    path(
        "<kind:kind>/<uuid:public_id>/annuler-validee/",
        views.cancel_approved,
        name="cancel_approved",
    ),
]
