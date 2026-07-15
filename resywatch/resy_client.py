"""A thin async client for Resy's (unofficial) private API.

These endpoints are the ones Resy's own website calls. They are not a
published/supported API, so field names can change without notice. Every
method is defensive about missing keys and raises ``ResyError`` with context
so the polling loop can log and carry on.

Respect Resy's Terms of Service: this is intended for light, personal use.
Keep poll intervals reasonable and do not hammer the endpoints.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import httpx

from .models import Slot, Venue

RESY_BASE = "https://api.resy.com"

# Public API key used by resy.com's web client. Override in config if needed.
DEFAULT_API_KEY = "VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class ResyError(Exception):
    """Any failure talking to Resy."""


class ResyClient:
    def __init__(
        self,
        api_key: str | None = None,
        auth_token: str | None = None,
        email: str | None = None,
        password: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key or DEFAULT_API_KEY
        self.auth_token = auth_token
        self.email = email
        self.password = password
        self._client = httpx.AsyncClient(
            timeout=timeout, headers=self._base_headers()
        )

    def _base_headers(self) -> dict[str, str]:
        return {
            "Authorization": f'ResyAPI api_key="{self.api_key}"',
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://resy.com",
            "Referer": "https://resy.com/",
            "X-Origin": "https://resy.com",
        }

    def _auth_headers(self) -> dict[str, str]:
        if not self.auth_token:
            return {}
        return {
            "X-Resy-Auth-Token": self.auth_token,
            "X-Resy-Universal-Auth": self.auth_token,
        }

    async def login(self) -> str:
        """Ensure we have an auth token, logging in with email/password if given."""
        if self.auth_token:
            return self.auth_token
        if not (self.email and self.password):
            raise ResyError(
                "No Resy auth token and no email/password provided. "
                "Set resy.auth_token or resy.email/password in your config."
            )
        try:
            resp = await self._client.post(
                f"{RESY_BASE}/3/auth/password",
                data={"email": self.email, "password": self.password},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ResyError(f"Resy login failed: {exc}") from exc
        token = data.get("token")
        if not token:
            raise ResyError("Resy login succeeded but returned no token.")
        self.auth_token = token
        return token

    async def search_venues(self, query: str, limit: int = 10) -> list[Venue]:
        try:
            resp = await self._client.post(
                f"{RESY_BASE}/3/venuesearch/search",
                json={"query": query, "per_page": limit},
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ResyError(f"Venue search failed: {exc}") from exc

        hits = (data.get("search") or {}).get("hits") or []
        venues: list[Venue] = []
        for hit in hits:
            try:
                vid = int((hit.get("id") or {}).get("resy"))
            except (TypeError, ValueError):
                continue
            loc = (hit.get("location") or {}).get("name") or hit.get(
                "locality", ""
            )
            venues.append(Venue(id=vid, name=hit.get("name", "?"), location=loc))
        return venues

    async def find_slots(
        self, venue_id: int, day: date, party_size: int
    ) -> list[Slot]:
        """Return all open slots for a venue on a given day/party size."""
        params = {
            "lat": 0,
            "long": 0,
            "day": day.isoformat(),
            "party_size": party_size,
            "venue_id": venue_id,
        }
        try:
            resp = await self._client.get(
                f"{RESY_BASE}/4/find",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ResyError(f"find_slots failed for venue {venue_id}: {exc}") from exc

        venues = ((data.get("results") or {}).get("venues")) or []
        if not venues:
            return []
        venue = venues[0]
        venue_name = ((venue.get("venue") or {}).get("name")) or str(venue_id)

        slots: list[Slot] = []
        for raw in venue.get("slots") or []:
            cfg = raw.get("config") or {}
            token = cfg.get("token")
            if not token:
                continue
            start_str = ((raw.get("date") or {}).get("start")) or ""
            try:
                start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            slots.append(
                Slot(
                    venue_id=venue_id,
                    venue_name=venue_name,
                    day=day,
                    start=start,
                    table_type=cfg.get("type", "Standard"),
                    party_size=party_size,
                    config_token=token,
                )
            )
        return slots

    async def get_book_token(
        self, config_token: str, day: date, party_size: int
    ) -> tuple[str, int | None]:
        """Turn a slot's config token into a short-lived book token.

        Also returns the user's default payment method id if Resy includes it
        (venues with deposits/cancellation fees require one to book).
        """
        try:
            resp = await self._client.post(
                f"{RESY_BASE}/3/details",
                json={
                    "commit": 1,
                    "config_id": config_token,
                    "day": day.isoformat(),
                    "party_size": party_size,
                },
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ResyError(f"get_book_token failed: {exc}") from exc

        book_token = ((data.get("book_token") or {}).get("value"))
        if not book_token:
            raise ResyError("Resy details returned no book_token (slot gone?).")

        payment_id = None
        methods = ((data.get("user") or {}).get("payment_methods")) or []
        if methods:
            payment_id = methods[0].get("id")
        return book_token, payment_id

    async def book(
        self, book_token: str, payment_method_id: int | None = None
    ) -> dict:
        """Commit a booking. Returns Resy's confirmation payload."""
        form: dict[str, str] = {
            "book_token": book_token,
            "source_id": "resy.com-venue-details",
        }
        if payment_method_id is not None:
            form["struct_payment_method"] = json.dumps({"id": payment_method_id})
        try:
            resp = await self._client.post(
                f"{RESY_BASE}/3/book",
                data=form,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:400]
            raise ResyError(f"Booking failed ({exc.response.status_code}): {body}") from exc
        except httpx.HTTPError as exc:
            raise ResyError(f"Booking failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()
