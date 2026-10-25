from django.urls import path

from apps.core.models import Module
from apps.core.views import undo_action

from . import views

app_name = "interventions"

urlpatterns = [
    path("interventions/", views.report_list, name="list"),
    path("interventions/nouveau/", views.new, name="new"),
    path("interventions/enregistrer/", views.save, name="save"),
    path(
        "interventions/annuler/<str:token>/",
        undo_action,
        {"prefix": "interventions.", "module": Module.INTERVENTIONS},
        name="undo",
    ),
    path("interventions/<uuid:public_id>/", views.detail, name="detail"),
    path("interventions/<uuid:public_id>/modifier/", views.edit, name="edit"),
    path("interventions/<uuid:public_id>/envoyer/", views.send, name="send"),
    path(
        "interventions/<uuid:public_id>/valider/",
        views.decide,
        {"approve": True},
        name="approve",
    ),
    path(
        "interventions/<uuid:public_id>/complement/",
        views.decide,
        {"approve": False},
        name="request_changes",
    ),
    path("interventions/<uuid:public_id>/pdf/", views.report_pdf, name="pdf"),
]
