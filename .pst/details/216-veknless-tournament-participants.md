# 216 — VEKN-less legacy tournament participants

## Rule
**Participate in a tournament ⇒ you get a VEKN ID.** Old archon's `Register`
never enforced `vekn_id`, so a few players landed in finished tournaments with
no VEKN. The current ETL seeds them as VEKN-less soft-deleted shells; with the
client now hard-deleting tombstones (#215) their names render as a raw uid.
Fix: no VEKN-less member may remain a tournament participant.

## Scope (fully bounded from the prod dump — won't grow; the engine's
`VeknIdRequired` blocks new VEKN-less participants)
4 VEKN-less members, 9 refs (4 players-dict + 5 seating), 3 Finished rich events
(vekn evt 12784, 13209, one no-vekn). Two cases:
- **Matchable dup** — one member's name+locale matches real **VEKN 3390002**, in
  two old-archon registrations: the active player (played 3 rounds, seated) and
  a phantom (registered, never seated, organizer's email).
- **Genuinely VEKN-less** — two members with no VEKN account anywhere.

## Verified against the live VEKN API (read-only: search_players + fetch_event)
Resolved — the match-first question is answered, no longer an open prerequisite:
- **Morgan** (funeral wake, Granada): matches live **VEKN 3390002** "Morgan Nemo
  Alcázar Rebollo" (Granada) — exact name + city. → **remap**. The 2nd
  registration (organizer's email, registered/never seated) is a phantom → drop.
- **Araceli Ruiz Bruno / Lusca Torresmo**: **0 registry hits** — genuinely
  VEKN-less. Event 12784 on vekn.net = calendar only (`attendance 0, players []`,
  never reported). Event 13209's submitted report = 9 VEKN-bearing players with
  **Lusca dropped** (old archon excluded the VEKN-less player from the push,
  which is why vekn.net accepted it). → **allocate + push** (owner-approved).
- Registering these two does NOT re-submit the events: imported finished
  tournaments are stamped push-inert (`vekn_pushed_at`, #114), and member push is
  independent — so no "archon already submitted" conflict. Pre-existing data
  divergence (12784 has no vekn.net results; 13209 is 9 there vs 10 in our import)
  is inherited, not introduced here; officially reporting those results is an
  organizer call, out of scope.

## Played-vs-registered (verified) — the decisive refinement
Seating refs / rounds_played per ref (from the dump):
- Araceli (12784): 2 seating, 2 rounds, tp 42 → **played**.
- Lusca (13209): **0 seating, 0 rounds**, tp 0 → registered, never played.
- Morgan real (funeral): 3 seating, 3 rounds, tp 130 → **played**.
- Morgan phantom (funeral): **0 seating, 0 rounds**, tp 0 → registered, never played.

## General ETL rule (replaces the blanket allocate+push)
A VEKN-less player entry with **no round seating** = registration artifact →
**DROP** it (no seating/standings refs to fix; it never affected results). A
VEKN-less player **with** seating must be resolved: **match → remap**, else
**allocate + push**.

**Scope the drop to VEKN-LESS only — do NOT drop all zero-round players.** A
zero-round player is dropped because it's a VEKN-less orphan, not because it
played zero rounds. The new engine itself *keeps* zero-round no-shows / early
drop-outs (StartRound flips `Registered`→`Finished`; `DropOut`→`Finished`; both
stay in `players`) — they carry `payment_status`/attendance and are already
excluded from standings (built from seating only). A VEKN-bearing no-show is not
an orphan and must be left untouched, for consistency with engine semantics and
to preserve the payment/registration record. (Explicit `Unregister`/`RemovePlayer`
already `array_remove` in the engine; those never reach the import as players.)

## RTP is no-show-neutral (checked)
Dropping a zero-round player does NOT change anyone's rating: `ratings.py:71`
`_player_count` = "players with ≥1 round played", so no-shows are already
excluded from the field-size coefficient. This also matches vekn.net (the 13209
report has 9 players, Lusca dropped → field size 9 both sides). So dropping
Lusca is RTP-neutral and keeps us aligned with the vekn api data.
Legacy archon agrees too: `engine.ratings()` sets `size = len([p for p in
players if p.rounds_played > 0])` and `update_tournament` recomputes it for every
finished tournament (imported included) — so the post-import rating recompute is
migration-stable, not just internally consistent.

## Net actions (in the ETL, re-applies on the prod cutover import)
- **Drop (2):** Lusca + Morgan phantom (0 seating). Dropping Lusca also makes the
  13209 import match vekn.net's official 9-player report.
- **Remap (1):** Morgan real → VEKN 3390002.
- **Allocate + push (1):** Araceli only (played 2 rounds; event 12784 never
  reported to vekn.net; genuinely VEKN-less).
1. **Participant pre-pass** (`migrate_from_archon.py`): one query over old
   `tournaments` collecting the set of member uids referenced by any tournament
   (`players` object keys ∪ `rounds[].tables[].seating[].player_uid`). Pass to
   member import.
2. **`merge_member` for a VEKN-less member:**
   - in `KNOWN_REMAP` (matched dup → real vekn) → don't seed; record
     `member_uid_map[old_uid] = live_uid_of(real_vekn)`.
   - in `KNOWN_DROP` (phantom registration) → don't seed; drop from tournament
     `players` at remap time (no seating ref to fix).
   - **else, if a tournament participant** → allocate a VEKN id
     (`allocate_next_vekn_id`), build a **live** VEKN-bearing user (not a shell),
     and mark **push-eligible** (`vekn_synced=False`) so `batch_push`/#114
     registers the id on vekn.net — claiming it so a future vekn.net assignment
     of that gap-filled id can't collide (#184 class).
   - else (non-participant VEKN-less) → `seed_vekn_less_shell` as today.
3. **`KNOWN_REMAP`/`KNOWN_DROP`** = small fixup tables keyed by old-archon uid
   (uids only — no names/emails; the public vekn 3390002 is the remap target).
4. **Idempotency**: on re-run, `get_user_by_uid(old_uid)` finds the now-live
   allocated/remapped member → skip allocation; the existing seed/merge guards
   (never modify an existing row / by-uid early-return) already cover this.
5. **`migrate_validate.py`**: live-member count expectation shifts by the number
   of allocated participants; add a check that no tournament player/seating ref
   resolves to a VEKN-less member post-run (the invariant this ticket enforces).

## Outward-facing side-effect (confirmed by owner)
Allocated participants are PUSHED to vekn.net → real official VEKN registrations.
Push is gated by VEKN_PUSH/#114 (on from #39 day one). Tiny volume (≤ a handful).

## Review / gates
principal-engineer (touches the just-reworked #115/#169 merge + push path +
external side-effect); senior-qa (ETL test + `migrate_validate` rerun); rerun
against the throwaway dump (probe recipe in
`migration-veknless-orphan-measured.md`) to confirm 0 VEKN-less participant refs.

## Acceptance
After ETL on the prod dump: 0 tournament refs resolve to a VEKN-less member; the
matched dup's results attribute to VEKN 3390002; the 2 genuine participants are
live VEKN-bearing + queued for vekn.net push; non-participant VEKN-less members
remain shells; daily re-run is idempotent (no re-allocation, no new push).
