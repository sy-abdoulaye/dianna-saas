from django.shortcuts import render
from django.utils import timezone


def home(request):
    """Tableau de bord : en-tête au lot 1, blocs complétés aux lots 2 et 4
    (docs/modules/02-tableau-de-bord.md). Rien n'est affiché qui ne fonctionne pas encore."""
    return render(request, "dashboard/home.html", {"today": timezone.localdate()})
