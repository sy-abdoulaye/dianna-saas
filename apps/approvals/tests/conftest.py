from datetime import timedelta

from django.utils import timezone


def free_monday(offset_weeks=1):
    """N-ième semaine à venir sans jour férié du lundi au vendredi (T-16) : les tests
    qui déclarent du télétravail ne dépendent pas de la date d'exécution."""
    from apps.agenda.days import holidays_between

    today = timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    if offset_weeks == 0:
        return monday
    found = 0
    while found < offset_weeks:
        monday += timedelta(days=7)
        if not holidays_between(monday, monday + timedelta(days=4)):
            found += 1
    return monday


def next_weekday(offset_days=7, weekday=0):
    """Un jour ouvré à venir (lundi de la semaine suivante par défaut), dans une semaine sans
    jour férié."""
    weeks, extra = divmod(offset_days, 7)
    return free_monday(weeks) + timedelta(days=weekday + extra)
