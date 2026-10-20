from datetime import timedelta

from django.utils import timezone


def next_weekday(offset_days=7, weekday=0):
    """Un jour ouvré à venir (lundi de la semaine suivante par défaut)."""
    today = timezone.localdate()
    monday = today + timedelta(days=7 - today.weekday())
    return monday + timedelta(days=weekday + offset_days - 7)
