---
name: tournament-action-request-field-allowlist
description: TournamentActionRequest is an explicit field allowlist + a hand-written event_data builder; any key not in BOTH is silently dropped from /action (display_name is a live casualty; vekn_id is deliberately absent)
metadata:
  type: reference
---

`POST /tournaments/{uid}/action` has a **three-place asymmetry**. A key the Rust
`TournamentEvent` consumes reaches the engine only if it is declared as a field on
`TournamentActionRequest` (backend/src/routes/tournaments.py, ~line 1430) **and**
copied into `event_data` by the hand-written per-field block just below it. Pydantic
defaults to `extra="ignore"`, so anything else a client sends vanishes with no error.

Two consequences to check whenever reviewing an /action change:

- **Security (by design):** `vekn_id` is deliberately absent from the model, so a
  client-sent vekn_id can never reach the engine — the server injects it from the
  resolved user only. Both engine branches (`Register`/`AddPlayer` ~mod.rs:437/503,
  `CheckIn` walk-in ~:625) also reject an empty/missing vekn_id, so an unresolvable
  `user_uid` was already a hard reject. Any proposal to add `vekn_id` to the request
  model reopens the fabricated-id hole.
- **Live bug (opposite direction):** `display_name` (Player field, models.py:476 —
  the Discord guild nickname) is NOT on the model. The bot sends it on Register and
  CheckIn (`bot/src/archon_bot/commands/player.py:96,181`) and the engine sets
  `player["display_name"]`, but the route drops it — so `Player.display_name` is
  always None in production and both consumers (`_seat_display`'s nickname branch in
  routes/tournaments.py, `bot/announcements.py:47`) are effectively dead code.
  Nothing else in the stack ever sets it.

Related: [[config-field-create-updateconfig-asymmetry]] (same shape for tournament
config fields).
