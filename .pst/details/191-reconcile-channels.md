# 191 — Unify bot channel management into one idempotent reconcile

Children: #192 (Phase 1 pure fns) · #193 (Phase 2 reconcile_channels, **closes #183**) · #194 (Phase 2 lock) · #195 (Phase 3 `/sync`)

## Problem

`bot/src/archon_bot/sse_listener.py::_handle_update` is the single most bug-prone file in the
repo (every recent bot commit touches it: round-prefixed names, SSE wedge, close-on-round-close,
the #183 add-table idempotency gap) and it has **no CI** (#156 — a runtime crash ships green).
It tangles **two concerns** that have opposite idempotency properties:

| Concern | Idempotent? | Today |
|---|---|---|
| **Structural** — which round/finals voice channels exist + per-member CONNECT/SPEAK perms | yes — pure function of tournament state | spread across `_setup_round` (two modes), `_setup_finals`, `_cleanup_round_channels`, `_reconcile`, and the mid-round add/remove-table block (~`:786`) |
| **Announcements** — seating, standings, score-reported, sanction, judge-call posts | no — edge-triggered; need prev/cur diff (re-posting "Round 2 seating" is spam; `compute_result_announcements` *cannot* be derived from current state alone) | also in `_handle_update`, interleaved with the structural work |

The codebase is already ~70% converged on a reconcile model — `fetch_round_channel_ids`
(`channel_manager.py:248`) discovers channels from Discord instead of trusting memory,
`sync_table_permissions` (`:87`) is already a full idempotent per-channel perm reconcile, and
`_setup_round(new_round=False)` / `_setup_finals` / `_reconcile` already re-adopt on reconnect.
This epic finishes the migration: one structural authority, announcements left as a separate
edge-triggered layer.

## Design

**The seam = structural vs announcement.** Only the structural half collapses into one function.

```
on tournament SSE event:
    if structure_signature(prev) != structure_signature(obj):   # cheap guard — skip per-score churn
        async with lock(tuid):
            link = store.get_tournament_link(...)   # RE-READ after acquire (#194)
            await reconcile_channels(bot, store, guild, tuid, obj)
    await emit_announcements(prev, obj)             # edge-triggered, stays diff-based
    _last_* = obj

_reconcile (reconnect)  -> lock + reconcile_channels   (replaces the _setup_* calls)
/teardown               -> lock + delete path
/sync (new, #195)       -> lock + reconcile_channels
```

- **`desired_channels(obj)`** (pure, #192): the deterministic target voice-channel set — ordered
  `R{n} - Table {m}` per current-round table, or a single `Finals` when `finals.seating` is present
  and has no result; each with its desired member set (`seated player_uids | organizer_uids`) over
  the `@everyone DENY CONNECT` baseline. Empty when state != Playing.
- **`structure_signature(obj)`** (pure, #192): hashable key over **structure-affecting fields only**
  — per-table membership sets + organizer set + finals/prelim mode. **Not table counts** (see
  amendment 1).
- **`reconcile_channels(...)`** (#193): diff `desired_channels(obj)` against ONE
  `fetch_guild_channels` call, **matching by channel name**; create missing, delete extra,
  perm-sync changed. Sole authority — absorbs all five structural code paths above.

## Principal-engineer review — verdict & amendments

**Endorsed.** The structural-vs-announcement seam is the right cut and it **kills #183 by
construction** (the add-table path stops existing as a special case). Keep v1 scope. Phase it with
the two pure functions as the merge gate, and land outside the #35/#39 migration window.

**Amendments (folded into the child tickets):**
1. **Signature keys on membership, not counts.** A count-only signature misses a same-size seat
   swap (same number of tables, different players) — that must still trigger a perm reconcile.
   Key on per-table membership sets + organizers + finals/prelim mode. (#192)
2. **Diff by channel *name*, not count.** Name-matching is what makes a timed-out *partial* create
   idempotent — a count-based diff re-creates duplicates after a partial failure. (#193)
3. **Lock is module-level and covers ALL structural mutation**, not just `/sync`: the
   `_handle_update` structural block, `_reconcile` (a reconnect can overlap a live event),
   `/teardown`'s delete path, and `/sync`. The holder must **re-read `get_tournament_link` after
   acquiring** — the link may have been torn down while it waited. (#194)

**Hard requirement (review risk #1 — cost model).** The "no per-channel fetch" efficiency win is
real *only if* `reconcile_channels` threads the overwrites already present on the
`fetch_guild_channels` payload into every `sync_table_permissions` call via `current_member_ids`.
As written, `sync_table_permissions` falls back to its own per-channel `fetch_channel` when that
arg is `None` (`channel_manager.py:113`), so the savings evaporate unless reconcile passes them
through. (`GuildVoiceChannel.permission_overwrites` is populated on the REST list payload in
hikari 2.5.0 — verified.) (#193)

## v1 scope (deliberately cut)

- **In:** the volatile round/finals voice channels + their perms (where all the bugs are).
- **Out:** reconciling the category / `#announcement` / `#lobby` / `#judges`. Recreating a
  manually-deleted text channel means mutating the stored link with a new channel id — extra
  complexity, deferred. **But** if `reconcile_channels` finds the *category itself* gone, it must
  abort and notify `#judges` rather than silently recreating an unparented mess.

## Failure modes to keep covered (regression checklist for #193)

- Partial/timed-out create -> next reconcile converges with no duplicates (name-diff).
- Bot restart (in-memory maps empty) -> reconcile re-adopts existing channels silently.
- Round close while disconnected -> leftover channels deleted on reconnect (today's
  `_reconcile` Waiting/Finished cleanup must survive the rewrite).
- Finals: prelim `Table N` channels must NOT linger during finals (map holds only the finals
  channel — today's `_setup_finals` invariant).
- Late Discord-linker gains table access via `/sync` (or next reconcile) without a reconnect.
- `/teardown` racing `/sync`/reconcile -> serialized by the lock; teardown wins (link gone ->
  reconcile no-ops after re-read).

## Sequencing

1. **#192** pure `desired_channels` + `structure_signature` + unit tests — **merge gate** (the
   only unit-testable surface; mirrors `test_fetch_round_channel_ids.py` /
   `test_teardown_tournament.py`). No behaviour change.
2. **#193** `reconcile_channels` + rewire all five structural paths + **#194** lock. Closes #183.
3. **#195** `/sync` command.

Land after the beta->prod migration (#39/#35) settles — this is the safety-critical SSE->Discord
path and bot CI (#156) is still absent, so the pure-function tests in #192 are the gate.
