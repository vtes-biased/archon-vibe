"""Web Push (#314): VAPID config, payload building, and delivery.

Push subscriptions are server-side send credentials in the ``push_subscriptions`` side
table — NOT the synced objects pipeline (they're endpoints the backend sends to, never
display data). This module loads the VAPID keypair from the environment, builds the three
notification types (seating, announcement, judge call), and delivers them with
``pywebpush.webpush_async`` over a single shared ``aiohttp.ClientSession``. The session's
TCPConnector pools connections per push host (most Chrome subs share fcm.googleapis.com),
so a fan-out reuses keep-alive connections instead of a fresh TLS handshake per push;
``limit`` / ``limit_per_host`` bound concurrency on the small box. (pywebpush owns the
RFC 8291 payload encryption + RFC 8292 VAPID signing — the crypto we must not hand-roll.)

Callers fire sends as ``asyncio.create_task`` AFTER a tournament transaction commits — a
delivery failure must never fail or delay the action response, and a DB-touching task
must never run inside ``tournament_transaction`` (the connection-owner guard). Dead
subscriptions are pruned on 404/410; other failures are transient and left in place.

The feature degrades gracefully: with no VAPID keys configured, ``is_configured()`` is
False and every send is a no-op (dev without keys, or an env before the vault entry).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import aiohttp
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush_async

from . import db
from .models import Tournament

logger = logging.getLogger(__name__)

# A large announcement can target hundreds of subscriptions; the box is small (DB pool
# max_size=20), so bound concurrent push connections — total and per push host.
_MAX_CONNECTIONS = 16
_MAX_CONNECTIONS_PER_HOST = 8
_REQUEST_TIMEOUT_S = 10
_TTL_SECONDS = 12 * 60 * 60  # push service holds undelivered up to 12h, then drops

_VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "")
_VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
_VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")

_vapid: Vapid02 | None = None
if _VAPID_PRIVATE_KEY and _VAPID_SUBJECT:
    try:
        _vapid = Vapid02.from_raw(_VAPID_PRIVATE_KEY.encode())
    except Exception as e:  # noqa: BLE001 - a bad key must not crash startup
        logger.error("Invalid VAPID_PRIVATE_KEY; Web Push disabled: %s", e)
elif _VAPID_PRIVATE_KEY or _VAPID_PUBLIC_KEY:
    logger.warning(
        "Web Push partially configured; needs VAPID_PRIVATE_KEY + VAPID_SUBJECT"
    )


def is_configured() -> bool:
    return _vapid is not None


def vapid_public_key() -> str:
    """The applicationServerKey (base64url) the browser subscribes with. Per-env."""
    return _VAPID_PUBLIC_KEY


# --- Localized message templates ----------------------------------------------
#
# Only the TEMPLATED bodies are localized. The announcement body is organizer free
# text (rendered as typed); a title that is a tournament name isn't translatable.
# Bodies render per-SUBSCRIPTION (a user may carry a FR phone and an EN laptop),
# keyed by the locale stored on each push_subscriptions row. en is the source; the
# other locales are maintained by the i18n-translator — keep the {placeholders} intact.

_FALLBACK_LOCALE = "en"

_PUSH_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "seating_round": "Round {round} — you're at Table {table}, seat {seat}.",
        "seating_finals": "Finals — you're at the table, seat {seat}.",
        "judge_title": "Judge call",
        "judge_body": "{player} needs a judge at {table}.",
    },
    "fr": {
        "seating_round": "Ronde {round} — vous êtes à la table {table}, siège {seat}.",
        "seating_finals": "Finale — vous êtes à la table, siège {seat}.",
        "judge_title": "Appel d'arbitre",
        "judge_body": "{player} demande un arbitre à {table}.",
    },
    "es": {
        "seating_round": "Ronda {round} — estás en la mesa {table}, asiento {seat}.",
        "seating_finals": "Final — estás en la mesa, asiento {seat}.",
        "judge_title": "Llamada al juez",
        "judge_body": "{player} necesita un juez en {table}.",
    },
    "pt": {
        "seating_round": "Rodada {round} — você está na mesa {table}, assento {seat}.",
        "seating_finals": "Final — você está na mesa, assento {seat}.",
        "judge_title": "Chamada de juiz",
        "judge_body": "{player} precisa de um juiz em {table}.",
    },
    "it": {
        "seating_round": "Round {round} — sei al tavolo {table}, posto {seat}.",
        "seating_finals": "Finale — sei al tavolo, posto {seat}.",
        "judge_title": "Chiamata giudice",
        "judge_body": "{player} chiede un giudice a {table}.",
    },
}


def _loc(locale: str | None) -> str:
    return locale if locale in _PUSH_MESSAGES else _FALLBACK_LOCALE


# --- Notification specs (pure data; localized at send time) --------------------


def build_seating_specs(t: Tournament, event_type: str) -> list[tuple[str, dict]]:
    """(user_uid, spec) for each player seated by a just-started round/finals.

    A *spec* is locale-independent data; ``render_payload(spec, locale)`` turns it into
    the wire notification. Enumerates ONLY the newly-appended round (``t.rounds[-1]``) or
    the finals table, so StartRound (all tables), SelfOrganizeRound (one pod), and
    StartFinals are uniform; a parallel-pod player who was not re-seated gets nothing.
    RestoreRound is excluded by the caller (it re-seats no one).
    """
    if event_type == "StartFinals":
        if t.finals is None:
            return []
        url = f"/tournaments/{t.uid}?finals=1"
        tag = f"seating-{t.uid}-finals"
        return [
            (
                seat.player_uid,
                {
                    "kind": "seating_finals",
                    "title": t.name,
                    "seat": i + 1,
                    "url": url,
                    "tag": tag,
                },
            )
            for i, seat in enumerate(t.finals.seating)
        ]

    if not t.rounds:
        return []
    round_no = len(t.rounds)
    tag = f"seating-{t.uid}-{round_no}"
    out: list[tuple[str, dict]] = []
    for table_idx, table in enumerate(t.rounds[-1]):
        for seat_idx, seat in enumerate(table.seating):
            out.append(
                (
                    seat.player_uid,
                    {
                        "kind": "seating_round",
                        "title": t.name,
                        "round": round_no,
                        "table": table_idx + 1,
                        "seat": seat_idx + 1,
                        "url": f"/tournaments/{t.uid}?table={table_idx + 1}",
                        "tag": tag,
                    },
                )
            )
    return out


def build_announcement_spec(t: Tournament, body: str) -> dict:
    # body is organizer free text — never localized.
    return {
        "kind": "announcement",
        "title": t.name,
        "body": body,
        "url": f"/tournaments/{t.uid}#announcements",
        "tag": f"announce-{t.uid}",
    }


def build_judge_call_spec(
    *,
    tournament_uid: str,
    tournament_name: str,
    table: int,
    table_label: str,
    player_name: str,
) -> dict:
    return {
        "kind": "judge",
        "title": tournament_name,
        "player": player_name,
        "table": table_label,
        "url": f"/tournaments/{tournament_uid}",
        "tag": f"judge-{tournament_uid}-{table}",
        # Re-alert even if a prior call at this table is still on screen — the
        # organizer must not miss a second player flagging the same table.
        "renotify": True,
    }


def render_payload(spec: dict, locale: str) -> dict:
    """Localize a notification spec into the wire payload for a subscription's locale."""
    m = _PUSH_MESSAGES[_loc(locale)]
    kind = spec["kind"]
    if kind == "seating_round":
        title = spec["title"]
        body = m["seating_round"].format(
            round=spec["round"], table=spec["table"], seat=spec["seat"]
        )
    elif kind == "seating_finals":
        title = spec["title"]
        body = m["seating_finals"].format(seat=spec["seat"])
    elif kind == "judge":
        title = f"{m['judge_title']} · {spec['title']}"
        body = m["judge_body"].format(player=spec["player"], table=spec["table"])
    else:  # announcement: tournament-name title, free-text body — neither localized
        title = spec["title"]
        body = spec["body"]
    payload = {"title": title, "body": body, "url": spec["url"], "tag": spec["tag"]}
    if spec.get("renotify"):
        payload["renotify"] = True
    return payload


# --- Delivery -----------------------------------------------------------------


async def send_to_users(targets: list[tuple[str, dict]]) -> None:
    """Deliver a per-user notification spec to every device the user subscribed,
    rendered in EACH subscription's own locale.

    ``targets`` is (user_uid, spec) pairs. Looks up all subscriptions for the target
    users in one query, then sends them over a single shared ``aiohttp.ClientSession``
    whose connector pools connections per push host, pruning rows on 404/410.
    """
    if not is_configured() or not targets:
        return
    by_user = dict(targets)
    subs = await db.get_push_subscriptions_for_users(list(by_user))
    if not subs:
        return

    async def _send(
        session: aiohttp.ClientSession,
        endpoint: str,
        user_uid: str,
        p256dh: str,
        auth: str,
        locale: str,
    ) -> None:
        spec = by_user.get(user_uid)
        if spec is None:
            return
        try:
            await webpush_async(
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {"p256dh": p256dh, "auth": auth},
                },
                data=json.dumps(render_payload(spec, locale)),
                vapid_private_key=_vapid,
                # Fresh claims per call: webpush mutates it in place (per-endpoint
                # `aud`/`exp`), so a shared dict would carry a stale audience.
                vapid_claims={"sub": _VAPID_SUBJECT},
                ttl=_TTL_SECONDS,
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S),
                aiohttp_session=session,
            )
        except WebPushException as e:
            status = getattr(e.response, "status", None)  # aiohttp ClientResponse
            if status in (404, 410):  # gone/unknown → endpoint is dead, prune it
                await db.delete_push_subscription(endpoint)
                logger.info("Pruned dead push subscription (HTTP %s)", status)
            else:  # 429/5xx/network = transient; keep the row
                logger.warning("Web Push send failed (HTTP %s): %s", status, e)
        except Exception as e:  # noqa: BLE001 - never let one send kill the gather
            logger.warning("Web Push send error: %s", e)

    # One session for the whole fan-out: the connector reuses keep-alive connections
    # per host (FCM/Mozilla/Apple) and bounds concurrency; closed when the batch ends.
    connector = aiohttp.TCPConnector(
        limit=_MAX_CONNECTIONS, limit_per_host=_MAX_CONNECTIONS_PER_HOST
    )
    async with aiohttp.ClientSession(connector=connector) as session:
        await asyncio.gather(
            *(_send(session, *s) for s in subs), return_exceptions=True
        )
