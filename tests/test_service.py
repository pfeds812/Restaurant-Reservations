"""End-to-end wiring test for the poll -> pending -> book flow, using a fake
Resy client so no network is touched.
"""
import asyncio
from datetime import date, datetime, time, timedelta

from resywatch.config import (
    Config,
    PollConfig,
    ResyConfig,
    ServerConfig,
)
from resywatch.models import Slot, Watch
from resywatch.notifier import Notifier
from resywatch.service import book_pending, poll_once
from resywatch.store import Store


class FakeResy:
    def __init__(self):
        self.booked = []
        day = date.today() + timedelta(days=3)
        self._slot = Slot(
            venue_id=1,
            venue_name="Carbone",
            day=day,
            start=datetime.combine(day, time(19, 30)),
            table_type="Dining Room",
            party_size=2,
            config_token="cfg-1",
        )

    async def find_slots(self, venue_id, day, party_size):
        # Only return the slot on its actual day.
        return [self._slot] if day == self._slot.day else []

    async def get_book_token(self, config_token, day, party_size):
        return "book-token-xyz", 555

    async def book(self, book_token, payment_method_id=None):
        self.booked.append((book_token, payment_method_id))
        return {"resy_token": "CONFIRMED-123"}


def make_config():
    day = date.today()
    return Config(
        resy=ResyConfig(),
        server=ServerConfig(public_url="http://x"),
        poll=PollConfig(per_request_delay=0, lookahead_days=30),
        notifications={"console": False},
        watches=[
            Watch(
                name="carbone",
                venue_id=1,
                party_size=2,
                date_from=day,
                date_to=day + timedelta(days=10),
                earliest_time=time(18, 0),
                latest_time=time(21, 0),
            )
        ],
    )


def test_poll_creates_pending_then_book(tmp_path):
    config = make_config()
    store = Store(str(tmp_path / "svc.db"))
    notifier = Notifier({"console": False})
    client = FakeResy()

    # First sweep finds the slot and creates exactly one pending confirmation.
    n = asyncio.run(poll_once(config, client, store, notifier))
    assert n == 1
    pending = store.list_pending("pending")
    assert len(pending) == 1

    # A second sweep must not re-alert (dedupe).
    n2 = asyncio.run(poll_once(config, client, store, notifier))
    assert n2 == 0

    # Confirming books via the (refreshed) token and marks it booked.
    row = store.get_pending(pending[0]["id"])
    ok, msg = asyncio.run(book_pending(row, client, store, notifier, None))
    assert ok is True
    assert "CONFIRMED-123" in msg
    assert client.booked == [("book-token-xyz", 555)]
    assert store.get_pending(pending[0]["id"])["status"] == "booked"


def test_auto_confirm_books_without_pending_action(tmp_path):
    config = make_config()
    config.watches[0].auto_confirm = True
    store = Store(str(tmp_path / "svc2.db"))
    notifier = Notifier({"console": False})
    client = FakeResy()

    asyncio.run(poll_once(config, client, store, notifier))
    booked = store.list_pending("booked")
    assert len(booked) == 1
    assert client.booked  # a booking actually happened
