"""Discord Guild Scheduled Event lifecycle for online tournaments.

One EXTERNAL scheduled event per linked *online* tournament, so server members
see it on the events list and get reminders. ``ensure_scheduled_event`` is the
single idempotent authority, keyed on the ``scheduled_event_id`` persisted in the
bot's ``guild_tournaments`` row — driven entirely off the tournament SSE snapshot
(no setup-time create path), so a bot restart never double-creates.
"""

import asyncio
import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import hikari

from . import config

logger = logging.getLogger(__name__)

# Fallback event length when the tournament carries no ``finish`` — a VTES day.
DEFAULT_DURATION = timedelta(hours=8)

# Discord field caps.
_NAME_MAX = 100
_DESC_MAX = 1000
_LOCATION_MAX = 100

# (guild:tournament) keys already told they're missing the events permission, so
# the one-line guidance posts once per process instead of on every ensure retry.
_perm_warned: set[str] = set()


@dataclass(frozen=True)
class EventSpec:
    """The scheduled event a tournament state requires."""

    name: str
    description: str
    location: str
    start: datetime  # tz-aware UTC
    end: datetime  # tz-aware UTC
    banner_path: str | None


def _parse_start(obj: dict) -> datetime | None:
    """Parse the tournament ``start`` into a tz-aware UTC datetime, defensively.

    The app's ``start`` may be an absolute instant (offset/``Z``) or a naive
    wall-clock time in ``timezone``; handle both — localize a naive value with the
    tournament's IANA zone, then normalize to UTC. Returns None if unset/unparseable.
    """
    raw = obj.get("start")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(obj.get("timezone") or "UTC"))
        except (ZoneInfoNotFoundError, ValueError):
            dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_end(obj: dict, start: datetime) -> datetime:
    """Event end: the tournament ``finish`` if set and after start, else a default."""
    raw = obj.get("finish")
    if raw:
        try:
            end = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if end.tzinfo is None:
                try:
                    end = end.replace(tzinfo=ZoneInfo(obj.get("timezone") or "UTC"))
                except (ZoneInfoNotFoundError, ValueError):
                    end = end.replace(tzinfo=UTC)
            end = end.astimezone(UTC)
            if end > start:
                return end
        except ValueError:
            pass
    return start + DEFAULT_DURATION


def _build_spec(obj: dict, tournament_uid: str) -> EventSpec | None:
    """The event a tournament requires, or None if it should have none.

    None when: not online, finished, soft-deleted, or no parseable start — the
    caller deletes any existing event in that case.
    """
    if not obj.get("online"):
        return None
    if obj.get("state") == "Finished" or obj.get("deleted_at"):
        return None
    start = _parse_start(obj)
    if start is None:
        return None

    name = (obj.get("name") or "Tournament")[:_NAME_MAX]
    url = f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
    fmt = obj.get("format")
    desc_parts = [f"{fmt} tournament." if fmt else "VTES tournament."]
    if obj.get("description"):
        desc_parts.append(str(obj["description"]))
    desc_parts.append(f"Details: {url}")
    description = "\n\n".join(desc_parts)[:_DESC_MAX]

    return EventSpec(
        name=name,
        description=description,
        location=url[:_LOCATION_MAX],
        start=start,
        end=_parse_end(obj, start),
        banner_path=obj.get("banner_path"),
    )


def event_signature(obj: dict) -> tuple:
    """Cheap digest of the fields that affect the scheduled event — the change guard.

    Equal between two snapshots ⇒ no ensure needed (skips score/seating churn)."""
    return (
        bool(obj.get("online")),
        obj.get("name"),
        obj.get("start"),
        obj.get("finish"),
        obj.get("banner_path"),
        obj.get("state"),
        # format + description feed the event description; without them a config
        # edit wouldn't re-ensure and the Discord event would keep a stale blurb.
        obj.get("format"),
        obj.get("description"),
        bool(obj.get("deleted_at")),
    )


def _to_png(data: bytes) -> bytes:
    """Transcode arbitrary image bytes (webp/png/jpeg) to PNG — sync/CPU bound."""
    from PIL import Image  # local import so a missing wheel can't break bot startup

    with Image.open(io.BytesIO(data)) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()


async def _fetch_cover(banner_path: str | None) -> hikari.Bytes | None:
    """Fetch the tournament banner and transcode it to a PNG event cover.

    Returns None (no cover) on any failure — the event is still created/edited.
    """
    if not banner_path:
        return None
    url = f"{config.ARCHON_URL}{banner_path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    logger.info(
                        "Banner fetch %s -> %s; no event cover", url, resp.status
                    )
                    return None
                raw = await resp.read()
        png = await asyncio.to_thread(_to_png, raw)
        return hikari.Bytes(png, "cover.png", mimetype="image/png")
    except Exception as e:
        logger.warning("Cover fetch/transcode failed for %s: %s", banner_path, e)
        return None


async def ensure_scheduled_event(
    bot,
    store,
    guild_id: str,
    tournament_uid: str,
    obj: dict,
    prev_obj: dict | None = None,
) -> None:
    """Idempotently drive Discord to the scheduled event ``obj`` requires.

    Create/edit/delete keyed on the stored ``scheduled_event_id``. Safe to call
    repeatedly (catch-up reconcile + live updates); failures are logged, never raised
    — a missing event is repaired on the next call. Caller should hold the structural
    lock so concurrent runs for one tournament don't race the stored id.

    ``prev_obj`` (the previous snapshot, when known) lets the banner be re-fetched
    only on an actual cover change instead of on every edit.

    Always attempted for online tournaments — a guild that didn't grant the bot
    MANAGE_EVENTS just makes the create ``ForbiddenError`` (logged, skipped).
    """
    link = await store.get_tournament_link(guild_id, tournament_uid)
    if not link:
        return
    event_id = link.get("scheduled_event_id")
    spec = _build_spec(obj, tournament_uid)
    gid = int(guild_id)

    # No event wanted (offline / finished / deleted / no start): remove any existing.
    if spec is None:
        if event_id:
            await _delete(bot, gid, event_id)
            await store.set_scheduled_event_id(guild_id, tournament_uid, None)
        return

    now = datetime.now(UTC)
    # Only (re)fetch + transcode the banner when it could actually have changed — a
    # fresh create, a reconcile with no prior snapshot, or a banner edit. A
    # name/description-only edit keeps the event's existing Discord cover.
    cover_changed = (
        event_id is None
        or prev_obj is None
        or prev_obj.get("banner_path") != obj.get("banner_path")
    )
    image = await _fetch_cover(spec.banner_path) if cover_changed else None

    # Edit the existing event when we still track one.
    if event_id:
        kwargs: dict = {
            "name": spec.name,
            "description": spec.description,
            "location": spec.location,
        }
        # Only move the schedule while the start is still in the future — Discord
        # rejects a past start, and a running event's start can't change.
        if spec.start > now:
            kwargs["start_time"] = spec.start
            kwargs["end_time"] = spec.end
        if image is not None:
            kwargs["image"] = image
        try:
            await bot.rest.edit_scheduled_event(gid, int(event_id), **kwargs)
            logger.info("Edited scheduled event %s for %s", event_id, tournament_uid)
            return
        except hikari.NotFoundError:
            # Deleted on Discord — fall through and recreate.
            logger.info("Scheduled event %s gone; recreating", event_id)
        except Exception as e:
            logger.warning("Edit scheduled event failed for %s: %s", tournament_uid, e)
            return

    # Create — Discord requires a future start.
    if spec.start <= now:
        logger.info(
            "Start not in the future; skipping event create for %s", tournament_uid
        )
        return
    try:
        kwargs = {"description": spec.description}
        if image is not None:
            kwargs["image"] = image
        ev = await bot.rest.create_external_event(
            gid, spec.name, spec.location, spec.start, spec.end, **kwargs
        )
        await store.set_scheduled_event_id(guild_id, tournament_uid, str(ev.id))
        logger.info("Created scheduled event %s for %s", ev.id, tournament_uid)
        _perm_warned.discard(f"{guild_id}:{tournament_uid}")  # reset on success
    except hikari.ForbiddenError:
        logger.warning(
            "Missing MANAGE_EVENTS — can't create scheduled event for %s",
            tournament_uid,
        )
        await _warn_missing_events_permission(bot, link, f"{guild_id}:{tournament_uid}")
    except Exception as e:
        logger.warning("Create scheduled event failed for %s: %s", tournament_uid, e)


async def _warn_missing_events_permission(bot, link: dict, key: str) -> None:
    """Post short, one-time guidance to #judges when the event couldn't be created.

    Deduped per (guild, tournament) per process so the repeated ensure calls don't
    spam; cleared on a later successful create (``ensure_scheduled_event``)."""
    if key in _perm_warned:
        return
    _perm_warned.add(key)
    judges_id = link.get("judges_channel_id")
    if not judges_id:
        return
    try:
        await bot.rest.create_message(
            int(judges_id),
            "ℹ️ I couldn't create a Discord event for this tournament. Grant me the "
            "**Manage Events** permission (Server Settings → Roles → my role); it'll "
            "be created automatically on the next update.",
        )
    except Exception as e:
        logger.warning("Failed to post event-permission guidance: %s", e)


async def _delete(bot, guild_id: int, event_id: str) -> None:
    """Delete a scheduled event, ignoring one already gone."""
    try:
        await bot.rest.delete_scheduled_event(guild_id, int(event_id))
        logger.info("Deleted scheduled event %s", event_id)
    except hikari.NotFoundError:
        pass
    except Exception as e:
        logger.warning("Delete scheduled event %s failed: %s", event_id, e)


async def delete_scheduled_event(
    bot, store, guild_id: str, tournament_uid: str
) -> None:
    """Remove a tournament's scheduled event and clear the stored id (for /teardown)."""
    link = await store.get_tournament_link(guild_id, tournament_uid)
    if not link:
        return
    event_id = link.get("scheduled_event_id")
    if not event_id:
        return
    await _delete(bot, int(guild_id), event_id)
    await store.set_scheduled_event_id(guild_id, tournament_uid, None)
