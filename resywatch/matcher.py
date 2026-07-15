"""Pure filtering/ranking logic for matching slots against a watch.

Kept free of I/O so it is easy to unit-test.
"""
from __future__ import annotations

from datetime import time

from .models import Slot, Watch

# Resy returns config types like "Dining Room", "Bar", "Patio", "Outdoor".
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _norm_dow(value: str) -> str:
    return value.strip()[:3].title()


def matches(watch: Watch, slot: Slot) -> bool:
    """Return True if a slot satisfies every constraint of the watch."""
    if slot.party_size != watch.party_size:
        return False

    t: time = slot.start.time()
    if not (watch.earliest_time <= t <= watch.latest_time):
        return False

    if watch.days_of_week:
        allowed = {_norm_dow(d) for d in watch.days_of_week}
        if _DOW[slot.day.weekday()] not in allowed:
            return False

    if watch.table_types:
        allowed_types = {tt.strip().lower() for tt in watch.table_types}
        if slot.table_type.strip().lower() not in allowed_types:
            return False

    return True


def rank_key(watch: Watch, slot: Slot):
    """Sort key: closest to preferred_time first, else earliest first."""
    if watch.preferred_time is not None:
        pref_seconds = (
            watch.preferred_time.hour * 3600
            + watch.preferred_time.minute * 60
        )
        slot_seconds = slot.start.hour * 3600 + slot.start.minute * 60
        return (abs(slot_seconds - pref_seconds), slot.start)
    return (0, slot.start)


def find_matches(watch: Watch, slots: list[Slot]) -> list[Slot]:
    """Filter and rank slots for a watch."""
    hits = [s for s in slots if matches(watch, s)]
    hits.sort(key=lambda s: rank_key(watch, s))
    return hits
