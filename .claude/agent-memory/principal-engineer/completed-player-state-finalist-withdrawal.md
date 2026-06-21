---
name: completed-player-state-finalist-withdrawal
description: Open-rounds + finalist-withdrawal forces a dedicated `Completed` PlayerState (cap-done, finals-eligible) distinct from `Finished` (withdrew, finals-ineligible); StartFinals must exclude {Disqualified, Finished}
metadata:
  type: project
---

The open-rounds per-player cap ([[open-rounds-per-player-cap]]) plus a **finalist-withdrawal** requirement (a top-5 player who drops must be excluded from finals, next-ranked promoted) forces a 6th `PlayerState` variant `Completed`. A single `Finished` can't carry both "done with prelims, present, finals-ELIGIBLE (cap reached)" and "gone, finals-INELIGIBLE (withdrew/dropped)".

**Why:** `StartFinals` (mod.rs:1619-1628) currently excludes only `Disqualified`, so a withdrawn (`Finished`) player is still eligible for top-5. To exclude withdrawals it must exclude `Finished` too — but `FinishRound` (mod.rs:831) already retires CAPPED players to `Finished`, so excluding `Finished` would wrongly drop the capped-but-present players. The two sub-cases must be different states. A `withdrawn: bool` flag on `Finished` was the alternative; rejected because the blast radius is the SAME (every player-state read still needs the boolean), and a state gets compile/grep-time surfacing that a silently-defaulting bool does not.

**How to apply (the ripple — every site that must handle `Completed`):**
- Engine is self-contained: ALL player-state string reads live in `mod.rs` + `raffle.rs` (+ `standings.rs` is state-AGNOSTIC, `sanctions.rs`/`scoring.rs`/`lib.rs` have ZERO player-state reads). Add to `PlayerState` from_str/as_str (types.rs:50-69).
- `StartFinals` (mod.rs:1625): change filter `ps != "Disqualified"` → `ps != "Disqualified" && ps != "Finished"`. Top-5 tie check `top5_has_ties(&standings)` (mod.rs:1633) runs on the FULL standings, not `eligible` — MUST realign to the eligible set or a withdrawn player's tie can falsely block finals (or a real tie among the promoted set goes unchecked).
- `FinishRound` (mod.rs:831): retire capped player to `"Completed"` not `"Finished"`.
- `DropOut` (mod.rs:434): rejects `Finished`; should ALSO accept `Completed`→`Finished` (a capped player choosing to withdraw from finals contention).
- `CheckIn` (mod.rs:506-510): already refuses re-check-in past cap via `PlayerReachedMaxRounds` — but the per-player guard is computed (rounds-played), so a `Completed` player hitting CheckIn is already blocked. Confirm `CheckInAll`(mod.rs:560)/`ResetCheckIn`(mod.rs:573) do NOT re-arm `Completed` (they only touch `Registered`/`Finished` — safe, but `Completed` must not be added to those branches).
- `CheckOut`(mod.rs:533), `SeatPlayer`(mod.rs:1157), `StartRound` pool(mod.rs:649): leave `Completed` out (a capped player shouldn't be seatable/checkout-able).
- `ReopenTournament`(mod.rs:262), `FinishFinals`(mod.rs:1717), `FinishTournament`(mod.rs:1742): these sweep non-DQ players to `Finished` — `Completed` players get swept to `Finished` correctly (tournament over). Confirm the reopen reset (`Finished`→`Checked-in`) handles `Completed` too if a capped player should be re-armed on reopen.
- Standings stay state-agnostic (`compute_preliminary_standings` iterates seating, never player.state) — a `Completed` player's prelim results still count/rank. No change needed. CONFIRMED.

**Cross-stack ripple:**
- Backend `PlayerState` is a real `StrEnum` (models.py:471-476), `Player.state` typed to it (msgspec). MUST add `COMPLETED = "Completed"` or msgspec decode rejects stored tournaments. Backward-compat: pre-existing tournaments have no `Completed`, so the addition is additive/safe; only NEW writes produce it.
- Frontend `PlayerState` union (types.ts:263) add `"Completed"`. `translatePlayerState` (tournament-utils.ts:245-253) add a case. The heuristic "completed vs dropped" display (`state==Finished && standings.some(uid)` at PlayerView.svelte:259-263, PlayersTab.svelte:529-537) should switch to checking `state==Completed` directly — that conflation is the bug `Completed` fixes.
- Counts/filters: `finishedPlayerCount` filters (`+page.svelte:236`, PlayersTab.svelte:325), active-set filter (`+page.svelte:258` `state!=="Finished" && !=="Disqualified"` — `Completed` players ARE active, must be included), RaffleSection.svelte:45 (`Checked-in`||`Playing` — capped players already raffleable via seating history in engine, but the FRONTEND raffle preview filter omits them; align if needed).
- i18n: add `player_state_completed` to all 5 message files (en/fr/it/es/pt ~line 186).
- Bot: only reads `state=="Checked-in"` (sse_listener.py:891) — no change unless `Completed` count wanted.
- access_levels.py does NOT touch player.state (full-object passthrough) — no change. CONFIRMED.
- No DB CHECK constraint on player state (JSONB) — no migration. CONFIRMED.
