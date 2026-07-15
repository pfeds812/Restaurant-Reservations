# resywatch

A personal background service that watches [Resy](https://resy.com) for
hard-to-get restaurant reservations (NYC + NJ) and pings you the instant a
matching slot opens — with a one-tap **Book it** button that completes the
reservation for you.

How it works:

1. You list the restaurants, dates, party sizes and time windows you want.
2. Every ~30s it polls Resy for each watch (cancellations show up here too).
3. On a match it grabs a fresh booking token, saves it, and notifies you.
4. You tap **Book it** → the local server finalizes the reservation.

> **Please read this.** Resy's Terms of Service prohibit automated access, and
> aggressive use can get your account banned. This tool is meant for *light,
> personal* use — modest poll intervals, your own account, booking tables you
> actually intend to keep. Keep `interval_seconds` reasonable and don't share
> your token. You are responsible for how you use it.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml     # edit this
cp .env.example .env                    # put secrets here
```

### Authenticating with Resy

Two options (pick one), configured in `config.yaml` / `.env`:

- **Auth token (simplest):** log in to resy.com in your browser, open
  DevTools → Network, click any request to `api.resy.com`, and copy the
  `x-resy-auth-token` request header. Put it in `.env` as `RESY_AUTH_TOKEN`.
- **Email + password:** set `RESY_EMAIL` / `RESY_PASSWORD` and leave the token
  blank; resywatch logs in for you.

### Finding venue IDs

```bash
python -m resywatch search "Carbone"
python -m resywatch search "Roberta's"
```

Copy the numeric ID into a `watches:` entry in `config.yaml`.

## Running

```bash
python -m resywatch watches     # sanity-check your configured watches
python -m resywatch run         # start polling + the confirm server
```

Then open <http://127.0.0.1:8787> to see found slots and book them from the
browser. When a slot appears you'll get a notification (see below).

## Notifications

- **ntfy (recommended for phone push):** install the free
  [ntfy](https://ntfy.sh) app, subscribe to an unguessable topic name, and set
  that topic in `config.yaml`. The push includes a **Book it** action button.
  For the button to reach your machine from your phone, set `server.public_url`
  to an address your phone can reach (e.g. a Tailscale IP or a tunnel).
- **Email:** enable the `email:` block (Gmail needs an
  [App Password](https://support.google.com/accounts/answer/185833)).
- **Console:** always on — you'll see matches in the log.

## Auto-book instead of confirming

Set `auto_confirm: true` on a watch to book the moment a match is found,
skipping the confirm step. Higher risk (mis-books, and more ToS exposure) —
use it only for watches where you're certain. Note that hard-to-get venues
usually require a card on file; set `resy.payment_method_id` or rely on your
Resy default.

## Layout

| File | Purpose |
|------|---------|
| `resywatch/resy_client.py` | Unofficial Resy API client (search / find / details / book) |
| `resywatch/matcher.py` | Pure slot filtering + ranking |
| `resywatch/service.py` | Polling loop and the shared booking routine |
| `resywatch/store.py` | SQLite: dedupe alerts + hold pending confirmations |
| `resywatch/notifier.py` | Console / ntfy / email notifications |
| `resywatch/web.py` | FastAPI confirm server + background poller |
| `resywatch/cli.py` | `search` / `watches` / `run` commands |

## Tests

```bash
pip install pytest
python -m pytest
```

## Roadmap ideas

- OpenTable / Tock support (for NJ suburbs and tasting menus)
- A "notify N minutes before booking windows drop" scheduler
- Telegram / SMS channels
- A small web UI to add/edit watches without editing YAML
