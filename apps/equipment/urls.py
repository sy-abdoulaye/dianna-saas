from django.urls import path

from . import views

app_name = "equipment"

urlpatterns = [
    path("materiel/", views.home, name="home"),
    path("materiel/parc/ajouter/", views.item_add, name="item_add"),
    path("materiel/parc/<uuid:public_id>/", views.item_detail, name="item_detail"),
    path("materiel/parc/<uuid:public_id>/attribuer/", views.item_assign, name="item_assign"),
    path("materiel/parc/<uuid:public_id>/restituer/", views.item_return, name="item_return"),
    path("materiel/parc/<uuid:public_id>/reparation/", views.item_repair, name="item_repair"),
    path("materiel/parc/<uuid:public_id>/fin-reparation/", views.item_back, name="item_back"),
    path("materiel/parc/<uuid:public_id>/retirer/", views.item_retire, name="item_retire"),
    path("materiel/annuler/<str:token>/", views.undo_action, name="undo"),
    path("materiel/equipements/<uuid:public_id>/signaler/", views.issue_new, name="issue_new"),
    path("materiel/signalements/<int:pk>/clore/", views.issue_close, name="issue_close"),
    path("materiel/signalements/<int:pk>/reparation/", views.issue_repair, name="issue_repair"),
    path(
        "materiel/demandes/<uuid:public_id>/attribuer/",
        views.request_assign,
        name="request_assign",
    ),
]
