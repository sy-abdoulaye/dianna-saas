from django.urls import path

from apps.core.models import Module
from apps.core.views import undo_action

from . import views

app_name = "careers"

urlpatterns = [
    path("carriere/", views.home, name="home"),
    path("carriere/lancer/", views.launch, name="launch"),
    path("carriere/campagne/", views.campaign, name="campaign"),
    path(
        "carriere/annuler/<str:token>/",
        undo_action,
        {"prefix": "careers.", "module": Module.CAREERS},
        name="undo",
    ),
    path("carriere/fiche/<uuid:public_id>/", views.follow_up_file, name="file"),
    path("carriere/fiche/<uuid:public_id>/note/", views.add_note, name="note"),
    path("carriere/fiche/<uuid:public_id>/pdf/", views.file_pdf, name="file_pdf"),
    path("carriere/<uuid:public_id>/", views.detail, name="detail"),
    path("carriere/<uuid:public_id>/auto-evaluation/", views.submit_self, name="self"),
    path("carriere/<uuid:public_id>/evaluation/", views.evaluate, name="evaluate"),
    path("carriere/<uuid:public_id>/planifier/", views.plan, name="plan"),
    path("carriere/<uuid:public_id>/realise/", views.held, name="held"),
    path("carriere/<uuid:public_id>/compte-rendu/", views.report, name="report"),
    path("carriere/<uuid:public_id>/signer/", views.sign, name="sign"),
    path("carriere/<uuid:public_id>/relancer/", views.remind, name="remind"),
    path("carriere/<uuid:public_id>/pdf/", views.review_pdf, name="pdf"),
]
