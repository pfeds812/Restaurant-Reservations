"""FastAPI app: serves the confirm endpoint and runs the poller in the background."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from html import escape

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from .config import Config
from .notifier import Notifier
from .resy_client import ResyClient
from .service import book_pending, poll_loop
from .store import Store

log = logging.getLogger("resywatch.web")


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
 body{{font-family:-apple-system,system-ui,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem;line-height:1.5}}
 .card{{border:1px solid #ddd;border-radius:12px;padding:1rem;margin:.75rem 0}}
 .ok{{color:#0a7d29}} .bad{{color:#b00020}}
 button{{background:#d5163b;color:#fff;border:0;border-radius:8px;padding:.6rem 1rem;font-size:1rem}}
 a.book{{display:inline-block;background:#d5163b;color:#fff;text-decoration:none;border-radius:8px;padding:.5rem .9rem}}
</style>
<h1>{escape(title)}</h1>
{body}
"""


def create_app(config: Config) -> FastAPI:
    store = Store(config.db_path)
    client = ResyClient(
        api_key=config.resy.api_key,
        auth_token=config.resy.auth_token,
        email=config.resy.email,
        password=config.resy.password,
    )
    notifier = Notifier(config.notifications)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await client.login()
            log.info("Authenticated with Resy.")
        except Exception as exc:  # noqa: BLE001 - surface but keep serving
            log.error("Resy auth failed at startup: %s", exc)
        task = asyncio.create_task(poll_loop(config, client, store, notifier))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await client.aclose()
            store.close()

    app = FastAPI(title="resywatch", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok", "watches": len(config.watches)}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        rows = store.list_pending(status=None)
        if not rows:
            body = "<p>No slots found yet. The poller is running.</p>"
        else:
            cards = []
            for r in rows:
                slot = store.slot_from_pending(r)
                status = r["status"]
                cls = {"booked": "ok", "failed": "bad", "expired": "bad"}.get(status, "")
                action = ""
                if status == "pending":
                    action = f'<p><a class="book" href="/confirm/{r["id"]}">Book it</a></p>'
                note = f' — {escape(r["note"])}' if r["note"] else ""
                cards.append(
                    f'<div class="card"><b>{escape(slot.describe())}</b>'
                    f'<p class="{cls}">status: {status}{note}</p>{action}</div>'
                )
            body = "".join(cards)
        return _page("resywatch — found slots", body)

    async def _do_confirm(pid: str):
        row = store.get_pending(pid)
        if row is None:
            return None
        return await book_pending(
            row, client, store, notifier, config.resy.payment_method_id
        )

    @app.get("/confirm/{pid}", response_class=HTMLResponse)
    async def confirm_get(pid: str):
        result = await _do_confirm(pid)
        if result is None:
            return HTMLResponse(_page("Not found", "<p>Unknown reservation.</p>"), 404)
        ok, message = result
        cls = "ok" if ok else "bad"
        return _page(
            "Booking result",
            f'<div class="card"><p class="{cls}">{escape(message)}</p></div>',
        )

    @app.post("/confirm/{pid}")
    async def confirm_post(pid: str):
        result = await _do_confirm(pid)
        if result is None:
            return JSONResponse({"ok": False, "error": "not found"}, 404)
        ok, message = result
        return JSONResponse({"ok": ok, "message": message})

    return app
