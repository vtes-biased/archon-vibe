---
name: open-rounds-per-player-cap
description: Per-player "open rounds" format design — max_rounds as a per-player cap, computed rounds-played gate, resting-state hazard with reusing Registered
metadata:
  type: project
---

Per-player "open rounds" format (non-VEKN, online scene). `max_rounds` becomes a per-player cap: each player plays *up to* `max_rounds` rounds out of a continuously-run pool; tournament may run more total rounds than `max_rounds`. Standings/finals unchanged (cumulative GW>VP>TP top-5); a maxed-out player stays finals-eligible. User chose the lightweight "computed gate" (rounds-played COMPUTED from seating appearances, no new player-state).

**Why:** user-confirmed product decision (overrides the older product-manager `project_open_rounds_semantics.md` "UI-only, no per-player tracking" note).

**How to apply:**
- Resting state for a maxed player is the live hazard. Reusing `Registered` is WRONG: PlayerView shows `Registered`+`Waiting` players the QR self-check-in button (`PlayerView.svelte:263`) and online re-check-in flow (`:291`), inviting a maxed player to re-check-in for a round they can't play; `CheckInAll`/`ResetCheckIn` also pump players back to `Registered`, so they'd be re-offered.
- SUPERSEDED (2026-06): the old "use `Finished`, distinguish via computed `played>=max && state==Finished` display" advice held ONLY while there was no finalist-withdrawal requirement. Once a top-5 player can withdraw and must be EXCLUDED from finals (next-ranked promoted), a single `Finished` can't carry both "done, finals-ELIGIBLE (capped)" and "gone, finals-INELIGIBLE (withdrew)". Verdict flipped to a dedicated `Completed` PlayerState — see [[completed-player-state-finalist-withdrawal]]. The heuristic display (`state==Finished && standings.some(uid)`) at PlayerView.svelte:259-263 / PlayersTab.svelte:529-537 is exactly the fragile conflation `Completed` removes.
- Standings already state-agnostic: `compute_preliminary_standings` (standings.rs) iterates rounds/seating, never player.state; `StartFinals` (mod.rs:1580) only filters `Disqualified`. A maxed player in any non-DQ state stays in top-5. Safe.
- Removing the tournament-wide `StartRound` guard (mod.rs:635 `MaxRoundsReached`): keep the `MaxRoundsReached` variant (cheap, still a valid taxonomy entry) OR remove if unused after — grep shows it's only thrown at mod.rs:636. `UpdateConfig`'s `MaxRoundsBelowCompleted` guard (mod.rs:1911) becomes wrong (total rounds can exceed cap); change it to compare against the *max per-player played count*, or drop the guard entirely for open-rounds.
- `CancelRound` decreases computed played-count → a maxed player auto-becomes eligible again. Correct with the computed approach (it's a pure function of seating), but means cancel un-maxes — acceptable.
- Frontend StartRound gate (`+page.svelte:819-826`) uses `rounds.length < maxRounds` (tournament-wide) — must change to "any checked-in player still under cap".
- Multideck deck slots (`PlayerDecksSection.svelte:52-55`) use tournament-wide `min(roundCount+1, maxRounds)` — must become the player's own played-count; `is_deck_locked` (helpers.rs:9) indexes decks by `rounds.len()` (tournament-wide) and is wrong per-player.
- vekn_push.py:144 `max_rounds if >=2 else len(rounds)` — for open-rounds push `len(rounds)` (actual total), not the per-player cap.
- Seating is safe: `select_players_for_round` (stagger.rs:106) only special-cases 6/7/11 and keys play_count off the current pool (`get_mut` no-ops for stale UIDs), so previous_rounds containing players not in the current subset is already handled.
