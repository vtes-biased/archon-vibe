"""Web Push (#314): VAPID config, payload building, and delivery.

Push subscriptions are server-side send credentials in the ``push_subscriptions`` side
table — NOT the synced objects pipeline (they're endpoints the backend sends to, never
display data). This module loads the VAPID keypair from the environment, builds the two
v1 notification payloads (seating, announcement), and fans sends out over the *blocking*
``pywebpush`` library via a bounded ``asyncio.to_thread`` offload.

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

from py_vapid import Vapid01
from pywebpush import WebPushException, webpush

from . import db
from .models import Tournament

logger = logging.getLogger(__name__)

# Bound the blocking webpush() offload: a large announcement could target hundreds of
# subscriptions, but the box is small (DB pool max_size=20) so cap concurrent sends.
_MAX_CONCURRENT_SENDS = 12
_TTL_SECONDS = 12 * 60 * 60  # push service holds undelivered up to 12h, then drops

_VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "")
_VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
_VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")

_vapid: Vapid01 | None = None
if _VAPID_PRIVATE_KEY and _VAPID_SUBJECT:
    try:
        _vapid = Vapid01.from_raw(_VAPID_PRIVATE_KEY.encode())
    except Exception as e:  # noqa: BLE001 - a bad key must not crash startup
        logger.error("Invalid VAPID_PRIVATE_KEY; Web Push disabled: %s", e)
elif _VAPID_PRIVATE_KEY or _VAPID_PUBLIC_KEY:
    logger.warning("Web Push partially configured; needs VAPID_PRIVATE_KEY + VAPID_SUBJECT")


def is_configured() -> bool:
    return _vapid is not None


def vapid_public_key() -> str:
    """The applicationServerKey (base64url) the browser subscribes with. Per-env."""
    return _VAPID_PUBLIC_KEY


# --- Payload builders (pure; the one part worth a unit test) ------------------


def build_seating_payloads(t: Tournament, event_type: str) -> list[tuple[str, dict]]:
    """(user_uid, payload) for each player seated by a just-started round/finals.

    Enumerates ONLY the newly-appended round (``t.rounds[-1]``) or the finals table, so
    StartRound (all tables), SelfOrganizeRound (one pod), and StartFinals are handled
    uniformly: a parallel-pod player who was not re-seated gets nothing. RestoreRound is
    excluded by the caller (it re-seats no one).
    """
    if event_type == "StartFinals":
        if t.finals is None:
            return []
        url = f"/tournaments/{t.uid}?finals=1"
        return [
            (
                seat.player_uid,
                {
                    "title": t.name,
                    "body": f"Finals — you're at the table, seat {i + 1}.",
                    "url": url,
                    "tag": f"seating-{t.uid}-finals",
                },
            )
            for i, seat in enumerate(t.finals.seating)
        ]

    if not t.rounds:
        return []
    round_no = len(t.rounds)
    out: list[tuple[str, dict]] = []
    for table_idx, table in enumerate(t.rounds[-1]):
        for seat_idx, seat in enumerate(table.seating):
            out.append(
                (
                    seat.player_uid,
                    {
                        "title": t.name,
                        "body": (
                            f"Round {round_no} — you're at Table {table_idx + 1}, "
                            f"seat {seat_idx + 1}."
                        ),
                        "url": f"/tournaments/{t.uid}?table={table_idx + 1}",
                        "tag": f"seating-{t.uid}-{round_no}",
                    },
                )
            )
    return out


def build_announcement_payload(t: Tournament, body: str) -> dict:
    return {
        "title": t.name,
        "body": body,
        "url": f"/tournaments/{t.uid}#announcements",
        "tag": f"announce-{t.uid}",
    }


def build_judge_call_payload(
    *, tournament_uid: str, tournament_name: str, table: int, table_label: str, player_name: str
) -> dict:
    return {
        "title": f"Judge call · {tournament_name}",
        "body": f"{player_name} needs a judge at {table_label}.",
        "url": f"/tournaments/{tournament_uid}",
        "tag": f"judge-{tournament_uid}-{table}",
        # Re-alert even if a prior call at this table is still on screen — the
        # organizer must not miss a second player flagging the same table.
        "renotify": True,
    }


# --- Delivery -----------------------------------------------------------------


async def send_to_users(targets: list[tuple[str, dict]]) -> None:
    """Deliver per-user payloads to every device each user has subscribed.

    ``targets`` is (user_uid, payload) pairs (one payload per user). Looks up all
    subscriptions for the target users in one query, then sends each via a bounded
    thread-pool offload of the blocking ``webpush`` call, pruning rows on 404/410.
    """
    if not is_configured() or not targets:
        return
    by_user = dict(targets)
    subs = await db.get_push_subscriptions_for_users(list(by_user))
    if not subs:
        return

    sem = asyncio.Semaphore(_MAX_CONCURRENT_SENDS)

    async def _send(endpoint: str, user_uid: str, p256dh: str, auth: str) -> None:
        payload = by_user.get(user_uid)
        if payload is None:
            return
        async with sem:
            try:
                await asyncio.to_thread(_webpush_sync, endpoint, p256dh, auth, payload)
            except WebPushException as e:
                status = getattr(e.response, "status_code", None)
                if status in (404, 410):  # gone/unknown → endpoint is dead, prune it
                    await db.delete_push_subscription(endpoint)
                    logger.info("Pruned dead push subscription (HTTP %s)", status)
                else:  # 429/5xx/network = transient; keep the row
                    logger.warning("Web Push send failed (HTTP %s): %s", status, e)
            except Exception as e:  # noqa: BLE001 - never let one send kill the gather
                logger.warning("Web Push send error: %s", e)

    await asyncio.gather(*(_send(*s) for s in subs), return_exceptions=True)


def _webpush_sync(endpoint: str, p256dh: str, auth: str, payload: dict) -> None:
    # Fresh vapid_claims dict per call: webpush() mutates it in place (sets per-endpoint
    # `aud` and `exp`), so a shared dict would carry a stale audience to the next send.
    webpush(
        subscription_info={
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
        },
        data=json.dumps(payload),
        vapid_private_key=_vapid,
        vapid_claims={"sub": _VAPID_SUBJECT},
        ttl=_TTL_SECONDS,
    )
