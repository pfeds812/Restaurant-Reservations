"""Notification channels: console, ntfy push, and email.

The push notification includes a one-tap "Book it" action that hits the
local /confirm/{id} endpoint.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from .models import Slot

log = logging.getLogger("resywatch.notify")


class Notifier:
    def __init__(self, notifications: dict) -> None:
        self.cfg = notifications or {}

    # --- public API -------------------------------------------------------
    def notify_match(self, slot: Slot, confirm_url: str) -> None:
        title = "🍽️  Resy slot found"
        body = f"{slot.describe()}\n\nTap to book: {confirm_url}"
        self._console(title, body)
        self._ntfy(title, slot.describe(), confirm_url)
        self._email(
            f"[resywatch] {slot.venue_name} available",
            f"{slot.describe()}\n\nBook it: {confirm_url}\n",
        )

    def notify_booked(self, slot: Slot, detail: str = "") -> None:
        title = "✅ Reservation booked"
        body = f"{slot.describe()}\n{detail}".strip()
        self._console(title, body)
        self._ntfy(title, body, None)
        self._email(f"[resywatch] Booked: {slot.venue_name}", body)

    def notify_failed(self, slot: Slot, reason: str) -> None:
        title = "⚠️ Booking failed"
        body = f"{slot.describe()}\n{reason}"
        self._console(title, body)
        self._ntfy(title, body, None)

    # --- channels ---------------------------------------------------------
    def _console(self, title: str, body: str) -> None:
        if self.cfg.get("console", True):
            log.info("%s\n%s", title, body)

    def _ntfy(self, title: str, body: str, confirm_url: str | None) -> None:
        ntfy = self.cfg.get("ntfy") or {}
        if not ntfy.get("enabled"):
            return
        server = (ntfy.get("server") or "https://ntfy.sh").rstrip("/")
        topic = ntfy.get("topic")
        if not topic:
            return
        headers = {"Title": title, "Priority": "high", "Tags": "fork_and_knife"}
        if confirm_url:
            # ntfy action button that POSTs to our confirm endpoint.
            headers["Actions"] = (
                f"http, Book it, {confirm_url}, method=POST, clear=true"
            )
        try:
            httpx.post(
                f"{server}/{topic}",
                data=body.encode("utf-8"),
                headers=headers,
                timeout=10,
            )
        except httpx.HTTPError as exc:
            log.warning("ntfy notification failed: %s", exc)

    def _email(self, subject: str, body: str) -> None:
        email = self.cfg.get("email") or {}
        if not email.get("enabled"):
            return
        required = ["smtp_host", "smtp_port", "from_addr", "to_addr"]
        if any(not email.get(k) for k in required):
            log.warning("email enabled but missing config; skipping")
            return
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = email["from_addr"]
        msg["To"] = email["to_addr"]
        try:
            with smtplib.SMTP(email["smtp_host"], int(email["smtp_port"]), timeout=15) as smtp:
                smtp.starttls()
                if email.get("username") and email.get("password"):
                    smtp.login(email["username"], email["password"])
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("email notification failed: %s", exc)
