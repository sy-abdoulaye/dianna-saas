from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("notifications/", views.notification_list, name="notifications"),
    path("notifications/<int:pk>/ouvrir/", views.notification_open, name="notification_open"),
    path("notifications/tout-lire/", views.notification_read_all, name="notifications_read_all"),
]
