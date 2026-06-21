# 266 — Per-player open-rounds support

## Decision (user-confirmed, informed)
"Open rounds" = a **per-player** round cap, a deliberately **non-VEKN** format that's gaining
traction on the online scene. Each player plays *up to* `max_rounds` rounds out of a
**continuously-run pool**; the tournament **MAY run more total rounds than `max_rounds`**, so at
any moment players sit at different round counts.

Chosen mechanism: **lightweight computed gate, NO new player state** (option 1). Rounds-played is
computed from seating, never stored.

This **overrides** `product-manager` memory `project_open_rounds_semantics.md` (which concluded
"UI-only, don't add per-player tracking"). The user accepts it's off-standard and that finals
seeding stays **cumulative** GW>VP>TP (the per-player cap bounds the unequal-rounds advantage;
averaged standings explicitly out of scope unless reopened).

## Engine design (engine/src/tournament/, pending principal-engineer sign-off)
- `count_player_rounds_played(tournament, uid)` helper = # rounds where uid appears in any table `seating`.
- `StartRound` (mod.rs:612-617): **remove** tournament-wide `rounds.len()>=max_rounds → MaxRoundsReached`;
  instead exclude over-cap players from the seating pool (mod.rs:619-632).
- `CheckIn` (mod.rs:447): reject at cap → new error `PlayerReachedMaxRounds` / `tournament.player_reached_max_rounds`.
- `CheckInAll` (mod.rs:540): skip over-cap players.
- `FinishRound` (mod.rs:778-794): a now-maxed Playing player → `Registered` (not `Checked-in`), so they don't linger pending.
- Standings/finals untouched: `StartFinals` (mod.rs:1580) filters only `Disqualified`, so maxed players (in Registered) stay finals-eligible.

## Open questions for principal-engineer (a093a72)
1. `Registered` resting state vs a computed "completed" display vs a real new state (user prefers no new state).
2. Confirm `compute_preliminary_standings` is state-agnostic (maxed/Registered players still ranked).
3. Ripple of removing the tournament-wide guard: `MaxRoundsReached` dead?; `MaxRoundsBelowCompleted` meaning under per-player; parallel rounds / AlterSeating / CancelRound (computed count auto-drops → re-eligible) / FinalsMinRounds.
4. Multideck `deckSlotCount` (PlayerDecksSection.svelte) is tournament-wide → must track per-player.
5. Seating optimizer `previous_rounds` history when a player wasn't in every prior round.
6. `hasUnequalRounds` warnings (now normal), VEKN push round count (vekn_push.py).

## Frontend
- Per-player `roundsPlayed(tournament, uid)` (tournament-utils.ts).
- PlayersTab/check-in: show `X/max`, disable check-in + "reached max" at cap.
- Between-rounds Waiting CTA (+page.svelte:785-794, 819-826): drop tournament-wide maxRounds gate; "Start round N+1" enabled while ≥4 under-cap players exist; steer to finals + fix guidance copy.
- error-codes.ts mapping for the new error.
- i18n ×5 (error, per-player guidance, hints).

## Docs to update (user asked)
- PRODUCT.md (tournament-core line ~258 + VEKN section ~275/347: clarify open-rounds = per-player, non-VEKN; max_rounds semantics).
- TOURNAMENTS.md (round/check-in/finals mechanics: per-player cap, total>max_rounds).
- README.md:190 VITE_VEKN_PUSH note if affected.
- PM memory `project_open_rounds_semantics.md`: rewrite to record the non-VEKN per-player decision (currently says don't implement).
- Config field copy `tfield_open_rounds*` (the description is now actually correct for this model — verify/keep).

## FINAL DESIGN (as implemented — supersedes the Finished-resting-state note below)
- Resting state = a **new `PlayerState::Completed`** (not Finished, not Registered). Reason: once
  finalist-withdrawal (#272) landed in scope, `Finished` had to mean "withdrew → finals-INELIGIBLE",
  so maxed players (finals-ELIGIBLE) need a distinct node. `Completed` = reached cap, done prelims,
  present, finals-eligible. Added to engine PlayerState, backend msgspec StrEnum, frontend union.
- `FinishRound` retires maxed → `Completed`; `StartFinals` excludes `{Disqualified, Finished}` (promotes
  next qualifier); `top5_has_ties` runs on the eligible set; `DropOut` works for `Completed` (→Finished);
  `CancelRound` re-arms `Completed` players dropped back under cap. Validated by principal-engineer (memory
  completed-player-state-finalist-withdrawal.md). All layers green; QA added the finals-withdrawal test.

## principal-engineer review outcome (FIRST pass — Finished-resting-state, later superseded above)
- Resting state = **`Finished`** (not Registered): Registered re-invites check-in (PlayerView:263/291) +
  CheckInAll/ResetCheckIn re-arm it → loop. `Finished` safe; add computed "completed — reached cap" display branch.
- New correctness catches: `is_deck_locked` (helpers.rs:9) indexes by tournament-wide rounds → make per-player
  (callers UpsertDeck mod.rs:1769, DeleteDeck :1813); `MaxRoundsBelowCompleted` guard → rebase on max per-player played-count.
- Confirmed safe: finals eligibility (standings state-agnostic, StartFinals filters only Disqualified), seating optimizer with partial history, cumulative standings under unequal rounds.
- Defaults chosen: no manual cap override (SeatPlayer stays Registered-only); vekn_push fixes round-count to len(rounds).
- Memory: .claude/agent-memory/principal-engineer/open-rounds-per-player-cap.md

## Children
- #267 engine (cap gate + is_deck_locked + UpdateConfig guard + error + 1 test)
- #268 frontend (roundsPlayed util, check-in disable/X-of-max, StartRound gate, hasUnequalRounds, PlayerView completed branch, deck slots, error-codes)
- #269 backend vekn_push round-count/has_finals
- #270 i18n ×5
- #271 docs (PRODUCT/TOURNAMENTS + config copy + rewrite PM memory)
