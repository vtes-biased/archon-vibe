---
name: bot-scoped-stream-frame-ordering
description: Bot scoped-stream pushes the tournament frame BEFORE participant User frames; live reconciles that need a participant's discord_id via the _user_names fallback race one message behind.
metadata:
  type: reference
---

On the Discord bot's tournament-scoped SSE stream, participant `user` frames
(carrying `User.discord_id`, member projection) arrive in a DIFFERENT order
between catch-up and live:

- **Catch-up (pre-`sync_complete`)**: `_scoped_catchup_frames` emits all
  participant+organizer user frames, THEN `sync_complete`. The bot's first
  reconcile runs only at `sync_complete`, so `_user_names[key]` is fully
  populated first. Safe.
- **Live (post-sync)**: `backend/src/main.py` yields the tournament `message`
  FIRST, then (if `conn.needs_participant_refresh`) the participant frames in
  the NEXT loop iteration. `broadcast.py` sets `needs_participant_refresh` on
  EVERY tournament delivery to a scoped conn.

**Trap:** any bot-side logic triggered by a tournament frame that resolves a
participant/organizer via the `_user_names` fallback (not the token store) is
racing — the needed user frame lands one SSE message LATER, and a `user`-type
event does NOT re-trigger a structural reconcile (`_handle_update` just caches
and returns). Concretely bites the #judges organizer sync (reconcile_channels):
a live-added organizer who linked Discord on the webapp but never ran /register
isn't granted judges access until the next structural reconcile, and gets a
spurious one-time "no linked Discord" warning. Self-heals via `/sync`
(`sync_now` reconciles the cached obj, by which time the frame is cached).

**Why:** `needs_participant_refresh` is cleared+fetched AFTER the tournament
message is yielded, to release the pool before yielding (the
`_overlay_frames`/`_scoped_catchup` no-yield-under-pool contract).

**How to apply:** when reviewing anything in `reconcile_channels` /
`_handle_update` that reads `_user_names[key]` for a uid that may have just
appeared in the tournament object (new organizer/player), assume the identity
cache is one message stale on the live path. Prefer token-store resolution
(present immediately) or re-sync on the subsequent `user` frame.
