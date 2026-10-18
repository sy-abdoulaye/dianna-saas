from django.urls import path

from . import dev_views

app_name = "dev"

urlpatterns = [
    path("styleguide/", dev_views.styleguide, name="styleguide"),
    path("styleguide/modale/", dev_views.demo_modal, name="modal"),
    path("styleguide/confirmation/", dev_views.demo_confirm, name="confirm"),
    path("styleguide/annuler/<str:token>/", dev_views.demo_undo, name="undo"),
    path("styleguide/notification/", dev_views.demo_toast, name="toast"),
    path("styleguide/pages/<slug:slug>/", dev_views.demo_page, name="page"),
    path("styleguide/erreur-serveur/", dev_views.demo_server_error, name="server_error"),
]
