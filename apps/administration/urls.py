from django.urls import path

from . import views

app_name = "administration"

urlpatterns = [
    path("administration/", views.company, name="company"),
    path("administration/competences/", views.competencies, name="competencies"),
    path("administration/competences/ajouter/", views.competency_form, name="competency_add"),
    path(
        "administration/competences/<int:pk>/modifier/",
        views.competency_form,
        name="competency_edit",
    ),
    path(
        "administration/competences/<int:pk>/monter/",
        views.competency_move,
        {"step": -1},
        name="competency_up",
    ),
    path(
        "administration/competences/<int:pk>/descendre/",
        views.competency_move,
        {"step": 1},
        name="competency_down",
    ),
    path(
        "administration/competences/<int:pk>/activation/",
        views.competency_toggle,
        name="competency_toggle",
    ),
    path("administration/utilisateurs/", views.users, name="users"),
    path(
        "administration/utilisateurs/<uuid:public_id>/profil/",
        views.change_role,
        name="change_role",
    ),
    path(
        "administration/utilisateurs/<uuid:public_id>/invitation/",
        views.send_invitation,
        name="send_invitation",
    ),
    path("administration/structure/", views.structure, name="structure"),
    path(
        "administration/structure/<str:kind>/ajouter/", views.structure_form, name="structure_add"
    ),
    path(
        "administration/structure/<str:kind>/<int:pk>/renommer/",
        views.structure_form,
        name="structure_rename",
    ),
    path(
        "administration/structure/<str:kind>/<int:pk>/supprimer/",
        views.structure_delete,
        name="structure_delete",
    ),
    path("administration/fermetures/", views.closures, name="closures"),
    path("administration/fermetures/ajouter/", views.closure_add, name="closure_add"),
    path(
        "administration/fermetures/<int:pk>/supprimer/",
        views.closure_delete,
        name="closure_delete",
    ),
    path("administration/modules/", views.modules, name="modules"),
    path("administration/modules/<str:module>/", views.toggle_module, name="toggle_module"),
    path("administration/journal/", views.journal, name="journal"),
    path("administration/journal/export/", views.journal_export, name="journal_export"),
]
