from django.urls import path

from . import views

app_name = "administration"

urlpatterns = [
    path("administration/", views.company, name="company"),
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
    path("administration/modules/", views.modules, name="modules"),
    path("administration/modules/<str:module>/", views.toggle_module, name="toggle_module"),
    path("administration/journal/", views.journal, name="journal"),
    path("administration/journal/export/", views.journal_export, name="journal_export"),
]
