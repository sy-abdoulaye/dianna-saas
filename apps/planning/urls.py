from django.urls import path

from . import views

app_name = "planning"

urlpatterns = [
    path("planning/", views.planning, name="week"),
    path("planning/export/", views.export, name="export"),
    path("planning/export/fichier/", views.download, name="download"),
]
