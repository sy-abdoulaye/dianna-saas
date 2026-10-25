"""Export iCalendar (RFC 5545), sans dépendance (L4-05) : un fichier .ics téléchargé.
L'abonnement par URL personnelle et révocable est prévu au lot 8."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.utils import timezone

from apps.core.dates import compact_day_stamp, ics_utc_stamp

ICS_CONTENT_TYPE = "text/calendar; charset=utf-8"


@dataclass(frozen=True)
class IcsEvent:
    uid: str
    start: date
    end: date  # dernier jour inclus
    summary: str
    tentative: bool = False


def escape(text: str) -> str:
    """Échappement des valeurs texte (RFC 5545, 3.3.11)."""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold(line: str) -> str:
    """Lignes de 75 octets au plus, suite précédée d'une espace (RFC 5545, 3.1)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        piece = char.encode("utf-8")
        limit = 75 if not parts else 74
        if len(current) + len(piece) > limit:
            parts.append(current.decode("utf-8"))
            current = b""
        current += piece
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def ics_content(events, *, name: str, stamp: datetime | None = None) -> str:
    stamp = ics_utc_stamp(stamp or timezone.now())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Dianna//Planning//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}",
    ]
    for event in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{escape(event.uid)}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{compact_day_stamp(event.start)}",
            f"DTEND;VALUE=DATE:{compact_day_stamp(event.end + timedelta(days=1))}",
            f"SUMMARY:{escape(event.summary)}",
            f"STATUS:{'TENTATIVE' if event.tentative else 'CONFIRMED'}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
