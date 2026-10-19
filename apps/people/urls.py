from django.urls import path

from . import views

app_name = "people"

urlpatterns = [
    path("annuaire/", views.DirectoryView.as_view(), name="list"),
    path("annuaire/nouveau/", views.EmployeeFormView.as_view(), name="create"),
    path("annuaire/import/", views.import_people, name="import"),
    path("annuaire/suggestions/", views.suggestions, name="suggestions"),
    path("annuaire/mes-coordonnees/", views.edit_contact, name="edit_contact"),
    path("annuaire/annuler/<str:token>/", views.undo_archive, name="undo"),
    path("annuaire/<uuid:public_id>/", views.EmployeeDetailView.as_view(), name="detail"),
    path("annuaire/<uuid:public_id>/modifier/", views.EmployeeFormView.as_view(), name="edit"),
    path("annuaire/<uuid:public_id>/archiver/", views.archive, name="archive"),
    path("annuaire/<uuid:public_id>/reactiver/", views.reactivate, name="reactivate"),
]
