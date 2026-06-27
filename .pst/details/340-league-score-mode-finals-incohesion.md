# VEKN import folds finals into standings — breaks the prelim-only contract

## Framing: archive consistency is the point; league Score is just a symptom

Project invariant: **`standings` = preliminary-only; finals live in the `finals` object;
rating/league scoring add finals on top** (`engine/src/league.rs`; spelled out in
`backend/src/archon_import.py:339-342`). Native tournaments honor it; so does the rich ETL
importer. **VEKN-API import is the one violator** — it folds `vpf` into `standings.vp` and the
winner's finals win (`+1`) into `standings.gw` (`vekn_tournament_sync.py:202-234`). The
imported record is therefore lossy and inconsistent with every other tournament in the archive
— you can't tell prelim from finals in a stored row, and the `standings` field silently means
something different for imports than for everything else. **That inconsistency is the issue.**

Direct sibling of **#79** (closed, p3): the exact same bug for the `archon_import` path
("writes finals-inclusive standings, breaking the prelim-only standings contract"), fixed by
writing prelim-only standings there. #340 finishes the job for the API importer.

Downstream symptom (one of several, not the headline): league **Score** mode sums the raw
standings row and skips the finals block (`league.rs:93-146`), so a mixed-origin Score league
double-counts finals for imported finalists only. Real but niche.

## Why this is harder than #79

#79's importer has **full rounds + finals** (rich xlsx), so prelim-only standings + a real
finals object "just works" and `compute_rating_vp_gw` still recovers the total via its
`has_play` (sum rounds + finals) path. **VEKN's API gives only a summary — no per-round data.**
Today the fold is *why* ratings work for imports: with `rounds` empty and `finals` null,
`compute_rating_vp_gw` reads the folded `standings` and gets the right total. Removing the fold
forces us to reconstruct a finals object AND teach the rating path to read prelim from
standings.

## Decision: Option A (reconstruct a finals object) — CONFIRMED

### 1. Importer (`vekn_tournament_sync.py`)
- `standings` → **prelim-only**: `vp = vp_prelim` (drop `+ vpf`), `gw = prelim_gw` (drop the
  winner `+1`), `tp`, `toss`; keep `finalist` (pos 1..5) and `winner` (pos==1).
- Build a `finals` `FinalsTable` **iff a final was actually played** — detect via
  `sum(vpf) > 0`. Seating = the finalists, each `result.vp = their vpf`, `result.gw = 1` for
  the winner else 0, `result.tp = compute_tp(size, vpf)` (positional, synthetic) or 0;
  `seed_order` = finalists by prelim rank; `state = "Finished"`. Seat order is synthetic
  (VEKN never gives it) — record/display only; nothing computes off it (winner + per-seat vpf
  are known).
- Old WITH-final events with `vpf=0` (e.g. event id=2, a CC with `rounds="0R"` and all
  `vpf=0`): no finals data → **no finals object**; standings prelim-only; the winner's
  tournament-win GW is handled by the rating rule below. Honest degradation — VEKN never gave
  us the finals detail, and its own `rtp` for those uses prelim VP only anyway.

### 2. Rating fn (engine `compute_rating_vp_gw`) — generalize
```
prelim_vp, prelim_gw = sum(rounds)   if rounds   else   read from standings   # now prelim-only
finals_vp,  finals_gw = sum(finals.seating for uid)   if finals   else   0
win_gw = 1 if (uid == winner AND finals absent) else 0   # tournament-win GW when no finals table recorded it
return (prelim_vp + finals_vp, prelim_gw + finals_gw + win_gw)
```
- WITH-final (native, or reconstructed import): `finals` present ⇒ `win_gw=0`; winner GW comes
  from the finals seat. Totals unchanged.
- NO-final import (winner set, no `finals`): `win_gw=1` ⇒ winner gets the tournament-win GW.
  Matches vekn.net (verified below).
- **Safe for native today**: a native no-final finish leaves `winner==""` (never set), so
  `win_gw=0` and native behavior is untouched until #341 deliberately sets a winner.

### 3. Net result
- `standings` is consistently prelim-only for native AND imports → **clean, honest archive**;
  an imported event with a final now carries a `finals` object like a native one.
- league **Score** = prelim-only on both sides (symptom fixed); RTP/GP add the now-present
  `finals` object → consistent shape, same totals.
- ratings produce the **same totals as today** for imports (must verify equal — see Review),
  now derived from a consistent record instead of a fold.

## Relationship to #341 (native no-final)

The `win_gw` rule is shared infrastructure. Once #341 (pending rules-director sign-off) makes
native `FinishTournament`-without-finals set `winner` + top-5 `finalist`, the SAME rating fn
credits native no-final winners automatically. So land #340's rating change first (needed for
import fidelity); #341 then reduces to just the engine `FinishTournament` change. #340 does not
change native behavior on its own (the `winner==""` guard). relates:#341 relates:#79

## Verified data — why we keep crediting finalists (incl. no-final)

Decomposed real per-player `rtp` (the VEKN event API returns it) against
`floor(5 + 4·(vp+vpf) + 8·(gw + [1 if winner])) + round(bonus·coef)`
(`engine/src/ratings.rs`), bonus = 90 winner / 30 ranks 2-5, coef = log15(pc²)−1+rank_bonus:
- **id=11775** (7p, `"3R"`, no final): winner gw1/vp3 → 72 = floor(5+12+8·**2**)+round(90·0.437);
  ranks 2-5 each +round(30·0.437)=+13. Exact.
- **id=10320** (14p, `"2R"`): winner +1 GW + round(90·0.949)=85; ranks 2-5 +28. Exact.
- Finals baselines (10000/10002/10003/10006) decompose identically with `vp+vpf` and winner
  `gw+1`. So vekn.net treats no-final events exactly like finals events with `vpf=0`.

Consequences for the design: (1) keep crediting no-final winner/top-5 — our imports already
match vekn.net and must continue to. (2) **Do NOT gate on `+F`** — and `+F`/`vpf` are
unreliable no-final markers for old events anyway (id=2 is a CC final with `rounds="0R"`,
`vpf=0`). (3) Some events have no results uploaded at all (id=10842 "2023 Irish Nationals":
`players:[]`) → import as Planned, contribute nothing; that's missing data, not exclusion.

## Review / risk

Cross-stack change: importer (Python) + the rating computation (Rust engine, consumed by both
PyO3 and WASM) → principal-engineer + senior-qa. Key regression gate: a sample of imported
events' `rtp`/rating must be **unchanged** before vs after (decompose a batch via the
throwaway scratchpad scripts). League Score/RTP/GP totals re-checked on a mixed-origin league.

## Implemented (verified) + review findings

Landed: importer writes prelim-only standings + reconstructs `finals` (`vekn_tournament_sync.py`),
engine `compute_rating_vp_gw` generalized with the `win_gw` rule (`standings.rs`), `ratings.py`
`_players_with_rounds` gates on `rounds` not `finals`, and the sync `changed` detector compares
`standings`/`finals` so legacy folded imports self-heal. Global RTP entry (points/vp/gw/fp/pc)
verified **unchanged** WITH- and NO-final. WASM unaffected (`compute_rating_vp_gw` is PyO3-only).
Native safe (`StartFinals` needs ≥2 rounds + `winner` only set in finals-finalization, so a
no-final native finish has `winner==""` → `win_gw` inert).

**DEPLOY SEQUENCING (rollout hazard — beta instances with legacy folded imports only).** The new
engine and importer are coupled: `win_gw` assumes prelim-only standings. A legacy folded import
not yet re-synced still has `finals=null` AND `standings.gw=prelim+1`, so the new engine
*double-counts* the winner's GW (folded +1, then `win_gw` +1) until the nightly VEKN sync heals
that row. A rating recompute in that window would *persist* the inflated GW. So on a beta deploy:
**run a full VEKN re-sync (the self-heal pass) before any rating recompute touches legacy imports.**
The self-heal pass re-broadcasts every healed import once (a bounded one-time SSE/write spike).
Not an issue for the prod migration (#39) — that's a fresh import with no legacy folded records.

**League RTP/GP *points* for imported finalists change (consistency, not regression).** `league.rs`
computes RTP points from the prelim-only standings base and only adds finals to *displayed* gw/vp
(`league.rs:113` vs `:137-146`). Pre-#340 imports had folded standings, so their league RTP points
accidentally *included* finals; native standings were always prelim-only, so native league RTP
*excluded* them. #340 alone left both prelim-only (consistent across origins, but diverging from
the global rating). The p3 follow-up **resolved the direction**: league **RTP** now uses the full
rating total (prelim + finals + the no-final win GW) so it matches the global/VEKN per-tournament
rating for native AND imports; league **Score** stays prelim-only (finals + win GW excluded), with
or without a final; GP points unchanged (placement-based). So league RTP no longer diverges.
