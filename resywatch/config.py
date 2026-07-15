"""Load and validate configuration from a YAML file (+ .env / environment)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time

import yaml

from .models import Watch

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(value):
    """Recursively expand ${ENV_VAR} references in strings."""
    if isinstance(value, str):
        had_ref = bool(_ENV_RE.search(value))
        expanded = _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
        # An unresolved reference (e.g. ${RESY_EMAIL} with no env var) collapses
        # to an empty string; treat that as "unset" so optional fields are None.
        if had_ref and expanded == "":
            return None
        return expanded
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def _parse_time(value, default: time) -> time:
    if value in (None, ""):
        return default
    return datetime.strptime(str(value), "%H:%M").time()


@dataclass
class ResyConfig:
    api_key: str | None = None
    auth_token: str | None = None
    email: str | None = None
    password: str | None = None
    payment_method_id: int | None = None


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    public_url: str = "http://127.0.0.1:8787"


@dataclass
class PollConfig:
    interval_seconds: int = 30
    jitter_seconds: int = 10
    lookahead_days: int = 30
    per_request_delay: float = 0.5


@dataclass
class Config:
    resy: ResyConfig
    server: ServerConfig
    poll: PollConfig
    notifications: dict
    watches: list[Watch]
    db_path: str = "resywatch.db"


def _load_watch(raw: dict) -> Watch:
    return Watch(
        name=raw["name"],
        venue_id=int(raw["venue_id"]),
        party_size=int(raw["party_size"]),
        date_from=date.fromisoformat(str(raw["date_from"])),
        date_to=date.fromisoformat(str(raw["date_to"])),
        earliest_time=_parse_time(raw.get("earliest_time"), time(0, 0)),
        latest_time=_parse_time(raw.get("latest_time"), time(23, 59)),
        preferred_time=_parse_time(raw.get("preferred_time"), None)
        if raw.get("preferred_time")
        else None,
        table_types=list(raw.get("table_types") or []),
        days_of_week=list(raw.get("days_of_week") or []),
        auto_confirm=bool(raw.get("auto_confirm", False)),
    )


def load_config(path: str = "config.yaml") -> Config:
    # Best-effort .env loading so RESY_* / SMTP_* are available.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    raw = _expand(raw)

    resy_raw = raw.get("resy") or {}
    pm = resy_raw.get("payment_method_id")
    resy = ResyConfig(
        api_key=resy_raw.get("api_key"),
        auth_token=resy_raw.get("auth_token"),
        email=resy_raw.get("email"),
        password=resy_raw.get("password"),
        payment_method_id=int(pm) if pm not in (None, "") else None,
    )

    srv_raw = raw.get("server") or {}
    server = ServerConfig(
        host=srv_raw.get("host", "127.0.0.1"),
        port=int(srv_raw.get("port", 8787)),
        public_url=srv_raw.get("public_url", "http://127.0.0.1:8787").rstrip("/"),
    )

    poll_raw = raw.get("poll") or {}
    poll = PollConfig(
        interval_seconds=int(poll_raw.get("interval_seconds", 30)),
        jitter_seconds=int(poll_raw.get("jitter_seconds", 10)),
        lookahead_days=int(poll_raw.get("lookahead_days", 30)),
        per_request_delay=float(poll_raw.get("per_request_delay", 0.5)),
    )

    watches = [_load_watch(w) for w in (raw.get("watches") or [])]

    return Config(
        resy=resy,
        server=server,
        poll=poll,
        notifications=raw.get("notifications") or {},
        watches=watches,
        db_path=raw.get("db_path", "resywatch.db"),
    )
