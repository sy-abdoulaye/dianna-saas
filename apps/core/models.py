from django.db import models
from django.utils.translation import gettext_lazy as _


class Timestamped(models.Model):
    """Horodatage de création et de modification, commun à tous les modèles (sauf exceptions
    documentées dans docs/03-modele-de-donnees.md, comme les réponses anonymes)."""

    created_at = models.DateTimeField(_("créé le"), auto_now_add=True)
    updated_at = models.DateTimeField(_("modifié le"), auto_now=True)

    class Meta:
        abstract = True
