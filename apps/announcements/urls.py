from django.urls import path

from apps.core.models import Module
from apps.core.views import undo_action

from . import views

app_name = "announcements"

urlpatterns = [
    path("annonces/", views.announcement_list, name="list"),
    path("annonces/nouvelle/", views.announcement_new, name="new"),
    path(
        "annonces/annuler/<str:token>/",
        undo_action,
        {
            "prefix": "announcements.",
            "module": Module.ANNOUNCEMENTS,
            "permission": "announcements.manage",
        },
        name="undo",
    ),
    path("annonces/<uuid:public_id>/", views.announcement_detail, name="detail"),
    path("annonces/<uuid:public_id>/modifier/", views.announcement_edit, name="edit"),
    path("annonces/<uuid:public_id>/epingler/", views.announcement_pin, name="pin"),
    path("annonces/<uuid:public_id>/supprimer/", views.announcement_delete, name="delete"),
]
