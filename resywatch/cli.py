"""Command-line entrypoint: search venues, list watches, run the service."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import load_config
from .resy_client import ResyClient, ResyError


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def _search(config, query: str, limit: int) -> None:
    client = ResyClient(
        api_key=config.resy.api_key,
        auth_token=config.resy.auth_token,
        email=config.resy.email,
        password=config.resy.password,
    )
    try:
        await client.login()
    except ResyError as exc:
        print(f"(warning) not authenticated: {exc}", file=sys.stderr)
    try:
        venues = await client.search_venues(query, limit)
    finally:
        await client.aclose()
    if not venues:
        print("No venues found.")
        return
    print(f"{'VENUE ID':>9}  NAME  (location)")
    for v in venues:
        loc = f"  ({v.location})" if v.location else ""
        print(f"{v.id:>9}  {v.name}{loc}")


def _list_watches(config) -> None:
    if not config.watches:
        print("No watches configured. Add some under 'watches:' in config.yaml.")
        return
    for w in config.watches:
        print(f"- {w.name}: venue {w.venue_id}, party {w.party_size}, "
              f"{w.date_from}..{w.date_to}, "
              f"{w.earliest_time:%H:%M}-{w.latest_time:%H:%M}"
              f"{' [auto]' if w.auto_confirm else ''}")


def _run(config) -> None:
    import uvicorn

    from .web import create_app

    app = create_app(config)
    print(f"resywatch running — open {config.server.public_url}")
    uvicorn.run(app, host=config.server.host, port=config.server.port, log_level="info")


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="resywatch", description="Resy reservation watcher")
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="find venue IDs by name")
    p_search.add_argument("query")
    p_search.add_argument("-n", "--limit", type=int, default=10)

    sub.add_parser("watches", help="list configured watches")
    sub.add_parser("run", help="start the polling service + confirm server")

    args = parser.parse_args(argv)
    config = load_config(args.config)

    if args.command == "search":
        asyncio.run(_search(config, args.query, args.limit))
    elif args.command == "watches":
        _list_watches(config)
    elif args.command == "run":
        _run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
