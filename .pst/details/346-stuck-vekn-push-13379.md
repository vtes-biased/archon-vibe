# #346 — Unsticking vekn event 13379 ("Infernal Summer")

Done 2026-08-08 on prod with `backend/scripts/fix_stuck_vekn_push.py --vekn 13379 --apply`.
Tournament uid `03959050-a259-402d-a420-6d342ecf66c3`.

## Two corrections to the plan this ticket carried

1. **It was `Playing`, not `Finished`.** The ticket assumed legacy's Finished state
   came across; it did not. That mattered because both `UNPUSHED_RESULTS_QUERY` and
   `push_tournament_results` are Finished-only, so clearing `vekn_pushed_at` alone
   would have left the hourly batch ignoring it forever. A `FinishTournament` was
   needed on top of the two steps the ticket listed.
2. **The step order was backwards.** The ticket said delete the round, then clear
   `vekn_pushed_at`. Done in that order *through the API*, the action route's
   write-once divergence guard (`routes/tournaments.py`, `if updated.vekn_pushed_at
   and not updated.vekn_results_stale` comparing `rounds`) stamps the sticky
   `vekn_results_stale` — i.e. "diverged from vekn.net" on results vekn.net never
   received. Clear the stamp first. The script bypasses the route, but keeps that
   order anyway.

Also worth knowing: **the UI cannot do this.** `isRoundCancellable`
(`frontend/src/routes/tournaments/[uid]/RoundsTab.svelte`) requires `Playing` AND
no finals; this event has finals. The engine allows it — `CancelRound` uses
`require_state_or_finished` and hard-removes the last round — so it has to go
through the API or a script. That is the "new engine allows the edit legacy
wouldn't" the ticket anticipated, but only via a non-UI path.

## Outcome

```
before: state=Playing  rounds=4 tables_per_round=[3,3,3,0] standings=15 vekn_pushed_at=2026-06-30
after:  state=Finished rounds=3 tables_per_round=[3,3,3]   standings=14 vekn_pushed_at=None
```

Winner unchanged (`019f1a00-8c0f-757a-99fd-6d54c335165a`, Juan José Romero
Paniagua). One deck op processed — a qualifying deck flipped public, which is why
the script reuses the route's `_process_deck_ops` instead of hand-writing SQL.

### Why standings went 15 → 14 (verified, not a loss)

Removing the round cannot explain it: round 4 held **zero tables**, and standings
are seating-derived. The real cause is that `update_standings` ran the *engine's*
computation over standings that were until then **migration-supplied by legacy**
and had never been engine-computed.

Miguel Ángel Ramos (`019f1a00-3351-74e0-96a1-47fe7ed1affc`) registered but never
sat at a table — `seats_played=0`, `in_finals=0`. Legacy counted him in standings;
the engine correctly excludes him, the same no-show case `generate_archondata`'s
own guard describes. Table sizes confirm 14 independently: rounds 1 and 2 are
5+5+4 = 14 seats. Round 3 is 5+4+4 = 13 because Javier de Haro Gonzalo played only
two rounds (`seats_played=2`).

This is worth remembering generally: **the first engine recompute of any
migration-supplied tournament can move its standings**, because legacy's roster and
the engine's seating-derived one disagree about no-shows. Check before pushing —
`upload_results` is write-once, so a wrong roster cannot be corrected via the API.

## Pre-flight that made this safe

`0` other Finished tournaments carry a trailing empty round, so this is a genuine
one-off and the script is deliberately targeted (`--vekn`/`--uid` required, never a
sweep) — a trailing empty round on a *Playing* tournament is also the normal
transient shape of a round an organizer has just opened but not yet seated.

The script refuses to apply when: no `external_ids.vekn` (a push would create a NEW
calendar event), the last round is not empty, removing it would leave 0 rounds, no
standings, **any sanctions** (they shift finals re-scoring, since
`refresh_finals_scoring` derives the finals round number from `rounds.len()`), or
**any player lacks a `vekn_id`** (`push_tournament_results` returns False silently,
so the push would no-op forever). This event had no sanctions and no missing
vekn_ids.

## Remaining

The next hourly `batch_push` uploads results to the **existing** calendar event
13379 — `external_ids.vekn` is set, so no duplicate event is created. Confirm
within the hour that `vekn_pushed_at` has been re-stamped (a real push, not the
2026-06-30 migration stamp) and that results show at
`vekn.net/event-calendar/event/13379`. If it did not fire, reopen.

The script is a one-off, like `fix_finish_before_start.py` before it (added in
`7136318`, deleted in `d5d77ea` once the root fix landed). There is no root cause to
fix here — legacy is frozen — so delete it once the push is confirmed.
