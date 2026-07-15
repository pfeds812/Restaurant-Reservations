"""The polling loop and the shared booking routine."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import date, timedelta

from .config import Config
from .matcher import find_matches
from .models import Slot
from .notifier import Notifier
from .resy_client import ResyClient, ResyError
from .store import Store

log = logging.getLogger("resywatch.service")

_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _watch_days(watch, lookahead_days: int):
    """Yield each date in the watch window, bounded by lookahead and today."""
    today = date.today()
    start = max(watch.date_from, today)
    end = min(watch.date_to, today + timedelta(days=lookahead_days))
    allowed = {d.strip()[:3].title() for d in watch.days_of_week} or None
    d = start
    while d <= end:
        if allowed is None or _DOW[d.weekday()] in allowed:
            yield d
        d += timedelta(days=1)


async def book_pending(
    row, client: ResyClient, store: Store, notifier: Notifier, payment_override: int | None
) -> tuple[bool, str]:
    """Book a held slot. Refreshes the book token first. Returns (ok, message)."""
    if row["status"] == "booked":
        return True, "Already booked."
    slot = store.slot_from_pending(row)

    # Re-fetch a fresh book token — stored ones expire quickly.
    book_token = row["book_token"]
    payment_id = payment_override if payment_override is not None else row["payment_id"]
    try:
        fresh_token, fresh_pm = await client.get_book_token(
            slot.config_token, slot.day, slot.party_size
        )
        book_token = fresh_token
        if payment_id is None:
            payment_id = fresh_pm
    except ResyError as exc:
        if not book_token:
            store.set_status(row["id"], "expired", str(exc))
            notifier.notify_failed(slot, f"Slot no longer available: {exc}")
            return False, f"Slot gone: {exc}"
        log.warning("Using stored book token; refresh failed: %s", exc)

    try:
        result = await client.book(book_token, payment_id)
    except ResyError as exc:
        store.set_status(row["id"], "failed", str(exc))
        notifier.notify_failed(slot, str(exc))
        return False, str(exc)

    resy_token = result.get("resy_token") or result.get("reservation_id") or ""
    store.set_status(row["id"], "booked", str(resy_token))
    notifier.notify_booked(slot, f"Confirmation: {resy_token}")
    return True, f"Booked! Confirmation: {resy_token}"


async def _process_slot(
    slot: Slot, watch, config, client, store, notifier
) -> None:
    store.mark_seen(slot.key())
    book_token = None
    payment_id = None
    try:
        book_token, payment_id = await client.get_book_token(
            slot.config_token, slot.day, slot.party_size
        )
    except ResyError as exc:
        log.warning("Could not pre-fetch book token for %s: %s", slot.describe(), exc)

    if config.resy.payment_method_id is not None:
        payment_id = config.resy.payment_method_id

    pid = store.add_pending(slot, book_token, payment_id)

    if watch.auto_confirm:
        log.info("Auto-confirming: %s", slot.describe())
        row = store.get_pending(pid)
        await book_pending(row, client, store, notifier, config.resy.payment_method_id)
    else:
        confirm_url = f"{config.server.public_url}/confirm/{pid}"
        notifier.notify_match(slot, confirm_url)


async def poll_once(config: Config, client, store, notifier) -> int:
    """Run one full sweep over all watches. Returns number of new matches."""
    new_matches = 0
    for watch in config.watches:
        for day in _watch_days(watch, config.poll.lookahead_days):
            try:
                slots = await client.find_slots(watch.venue_id, day, watch.party_size)
            except ResyError as exc:
                log.warning("find failed (%s, %s): %s", watch.name, day, exc)
                await asyncio.sleep(config.poll.per_request_delay)
                continue

            for slot in find_matches(watch, slots):
                if store.is_seen(slot.key()):
                    continue
                log.info("Match [%s]: %s", watch.name, slot.describe())
                new_matches += 1
                await _process_slot(slot, watch, config, client, store, notifier)

            await asyncio.sleep(config.poll.per_request_delay)
    return new_matches


async def poll_loop(config: Config, client, store, notifier) -> None:
    log.info("Poll loop started (%d watches).", len(config.watches))
    while True:
        try:
            store.prune_seen()
            await poll_once(config, client, store, notifier)
        except asyncio.CancelledError:
            raise
        except Exception:  # keep the daemon alive across unexpected errors
            log.exception("Unexpected error during poll sweep")
        delay = config.poll.interval_seconds + random.uniform(
            0, config.poll.jitter_seconds
        )
        await asyncio.sleep(delay)
