"""Core data models for resywatch."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time


@dataclass
class Venue:
    """A restaurant on Resy."""

    id: int
    name: str
    location: str = ""


@dataclass
class Slot:
    """A single bookable reservation slot returned by Resy's find endpoint."""

    venue_id: int
    venue_name: str
    day: date
    start: datetime
    table_type: str
    party_size: int
    config_token: str

    def key(self) -> str:
        """Stable identity used to dedupe alerts across polls."""
        return "|".join(
            [
                str(self.venue_id),
                self.day.isoformat(),
                self.start.isoformat(),
                self.table_type.lower(),
                str(self.party_size),
            ]
        )

    def describe(self) -> str:
        return (
            f"{self.venue_name} — {self.start.strftime('%a %b %-d, %-I:%M %p')} "
            f"({self.table_type}, party of {self.party_size})"
        )


@dataclass
class Watch:
    """A user's standing request to be alerted when a venue has matching slots."""

    name: str
    venue_id: int
    party_size: int
    date_from: date
    date_to: date
    earliest_time: time = time(0, 0)
    latest_time: time = time(23, 59)
    preferred_time: time | None = None
    table_types: list[str] = field(default_factory=list)
    days_of_week: list[str] = field(default_factory=list)
    auto_confirm: bool = False
