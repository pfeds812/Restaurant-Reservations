"""SQLite persistence: dedupe alerts and hold pending confirmations."""
from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import date, datetime

from .models import Slot


class Store:
    def __init__(self, path: str = "resywatch.db") -> None:
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen (
                key TEXT PRIMARY KEY,
                ts  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending (
                id            TEXT PRIMARY KEY,
                venue_id      INTEGER NOT NULL,
                venue_name    TEXT NOT NULL,
                day           TEXT NOT NULL,
                start_iso     TEXT NOT NULL,
                table_type    TEXT NOT NULL,
                party_size    INTEGER NOT NULL,
                config_token  TEXT NOT NULL,
                book_token    TEXT,
                payment_id    INTEGER,
                status        TEXT NOT NULL DEFAULT 'pending',
                note          TEXT DEFAULT '',
                created_at    REAL NOT NULL
            );
            """
        )
        self.conn.commit()

    # --- dedupe -----------------------------------------------------------
    def is_seen(self, key: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM seen WHERE key = ?", (key,))
        return cur.fetchone() is not None

    def mark_seen(self, key: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO seen(key, ts) VALUES (?, ?)",
            (key, time.time()),
        )
        self.conn.commit()

    def prune_seen(self, older_than_seconds: float = 7 * 86400) -> None:
        cutoff = time.time() - older_than_seconds
        self.conn.execute("DELETE FROM seen WHERE ts < ?", (cutoff,))
        self.conn.commit()

    # --- pending confirmations -------------------------------------------
    def add_pending(
        self, slot: Slot, book_token: str | None, payment_id: int | None
    ) -> str:
        pid = uuid.uuid4().hex[:12]
        self.conn.execute(
            """
            INSERT INTO pending (id, venue_id, venue_name, day, start_iso,
                table_type, party_size, config_token, book_token, payment_id,
                status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                pid,
                slot.venue_id,
                slot.venue_name,
                slot.day.isoformat(),
                slot.start.isoformat(),
                slot.table_type,
                slot.party_size,
                slot.config_token,
                book_token,
                payment_id,
                time.time(),
            ),
        )
        self.conn.commit()
        return pid

    def get_pending(self, pid: str) -> sqlite3.Row | None:
        cur = self.conn.execute("SELECT * FROM pending WHERE id = ?", (pid,))
        return cur.fetchone()

    def list_pending(self, status: str | None = "pending") -> list[sqlite3.Row]:
        if status is None:
            cur = self.conn.execute(
                "SELECT * FROM pending ORDER BY created_at DESC"
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM pending WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        return cur.fetchall()

    def set_status(self, pid: str, status: str, note: str = "") -> None:
        self.conn.execute(
            "UPDATE pending SET status = ?, note = ? WHERE id = ?",
            (status, note, pid),
        )
        self.conn.commit()

    def slot_from_pending(self, row: sqlite3.Row) -> Slot:
        return Slot(
            venue_id=row["venue_id"],
            venue_name=row["venue_name"],
            day=date.fromisoformat(row["day"]),
            start=datetime.fromisoformat(row["start_iso"]),
            table_type=row["table_type"],
            party_size=row["party_size"],
            config_token=row["config_token"],
        )

    def close(self) -> None:
        self.conn.close()
