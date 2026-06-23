# Discord scheduled event for online tournaments

Auto-create/maintain a Discord **Guild Scheduled Event** (EXTERNAL type) for each
linked **online** tournament, so server members see it on the events list and get
reminders. Bot-only; no backend/engine work.

## Event shape
- **type** EXTERNAL (the tournament runs on the webapp, not a Discord voice channel).
  `location` = the webapp tournament URL (`{ARCHON_FRONTEND_URL}/tournaments/{uid}`).
- **name** = tournament name (≤100 chars). **description** = format + tournament
  description + manage link (≤1000). **start_time** = parsed `start`. **end_time** =
  `finish` if set & after start, else `start + DEFAULT_DURATION` (8h, a VTES day).
- **cover image** = the tournament banner (#278), transcoded webp→PNG in the bot
  (Pillow) because Discord's event-cover data-URI accepts only PNG/JPEG/GIF, while
  the cropper outputs webp. Fetched from the public immutable `banner_path`; on any
  fetch/transcode/upload failure the event is created/edited WITHOUT a cover (graceful).

## `start`/`timezone` parsing
The wire form is a **naive** wall-clock (`"2026-07-15T14:00:00"`, no offset —
msgspec keeps naive datetimes naive) plus a separate IANA `timezone`
(verified end-to-end: `ConfigTab.svelte` `start.slice(0,16)` → backend `models.py`
→ msgspec). So `_parse_start` localizes the naive value with
`ZoneInfo(tournament.timezone)` then converts to UTC — the load-bearing path, not
just defensive (it also tolerates an absolute instant with offset/`Z`, harmlessly).
Discord requires a tz-aware, **future** `start_time` on CREATE.

## Lifecycle (idempotent, driven off SSE — no setup.py create path)
`ensure_scheduled_event(obj)` is the single authority, keyed on the
`scheduled_event_id` stored in the bot's `guild_tournaments` row:
- Called from the SSE **catch-up reconcile** (`_reconcile`) → initial create AND
  restart idempotency (stored id survives restart in SQLite, so no double-create).
- Called from **live updates** (`_handle_update`) when the event signature
  (online/name/start/finish/banner_path/state/deleted_at) changes → create/edit.
- **spec is None** (not online, Finished, soft-deleted, or no future start) and an
  id exists → delete the event + clear the id. This covers "complete/cancel on finish".
- CREATE needs a future start (Discord rejects past starts); EDIT omits start/end
  once start has passed (can't move a running event) and just refreshes name/desc/cover.
- **/teardown** deletes the event before unlinking.

## Gotchas
- **MANAGE_EVENTS** guild permission required — a DEPLOY/portal step (the bot's
  install/invite permissions, like Manage Channels for the voice tables). Always
  attempted (no env opt-in); a guild that didn't grant it just makes create/edit
  403 → `ForbiddenError`, handled gracefully (logged, event skipped), tournament
  unaffected. (Discord scheduled events are available to all guilds — no Community
  feature gate for external/voice events — and any other rejection hits the broad
  `except` the same way.) On the permission failure the bot posts ONE short hint to
  #judges ("grant me Manage Events…"), deduped per (guild, tournament) per process
  so the repeated ensure calls never spam.
- Bot has no i18n → plain English.
- Pillow decode is sync/CPU → run via `asyncio.to_thread` so it never blocks the loop.

relates:#277 relates:#173 relates:#278
