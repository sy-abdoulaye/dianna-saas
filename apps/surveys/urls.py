from django.urls import path

from . import views

app_name = "surveys"

urlpatterns = [
    path("questionnaires/", views.survey_list, name="list"),
    path("questionnaires/nouveau/", views.survey_new, name="new"),
    path("questionnaires/<uuid:public_id>/", views.survey_detail, name="detail"),
    path("questionnaires/<uuid:public_id>/repondre/", views.survey_answer, name="answer"),
    path("questionnaires/<uuid:public_id>/modifier/", views.survey_edit, name="edit"),
    path("questionnaires/<uuid:public_id>/publier/", views.survey_publish, name="publish"),
    path("questionnaires/<uuid:public_id>/clore/", views.survey_close, name="close"),
    path("questionnaires/<uuid:public_id>/supprimer/", views.survey_delete, name="delete"),
]
