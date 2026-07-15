from datetime import date, datetime

from resywatch.models import Slot
from resywatch.store import Store


def make_slot():
    return Slot(
        venue_id=42,
        venue_name="Carbone",
        day=date(2026, 7, 20),
        start=datetime(2026, 7, 20, 19, 30),
        table_type="Dining Room",
        party_size=2,
        config_token="cfgtok",
    )


def test_seen_dedupe(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    slot = make_slot()
    assert store.is_seen(slot.key()) is False
    store.mark_seen(slot.key())
    assert store.is_seen(slot.key()) is True


def test_pending_roundtrip_and_status(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    slot = make_slot()
    pid = store.add_pending(slot, book_token="bt", payment_id=99)

    row = store.get_pending(pid)
    assert row is not None
    assert row["status"] == "pending"
    assert row["book_token"] == "bt"
    assert row["payment_id"] == 99

    # Reconstruct the slot from the stored row.
    restored = store.slot_from_pending(row)
    assert restored.key() == slot.key()
    assert restored.venue_name == "Carbone"

    store.set_status(pid, "booked", "resy123")
    assert store.get_pending(pid)["status"] == "booked"
    assert len(store.list_pending(status="pending")) == 0
    assert len(store.list_pending(status=None)) == 1
