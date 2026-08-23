> Elaborated context for a line in `BOARD.md`. Deleted with the line.

# An imported standings sheet is not the engine's sheet

Doc-impact: the inbound Tournaments section of [`wiki/vekn.md`](../wiki/vekn.md),
and the imported-sheet rules in [`wiki/tournaments.md`](../wiki/tournaments.md)
(the no-show/DQ/proxy classes and the sheet ordering). The DQ-signal paragraph in
[`wiki/hazards.md`](../wiki/hazards.md) gains the inbound sync as a consumer if the
fix reads the combined signal there.

## The disqualification we are told about and throw away

vekn.net carries `dq` and `wd` per participant — see the event response in
`vekn-api/readme.md`, where every participant object holds `pos`, `wd` and `dq`.
Its own importer sets a flagged row's `pos` to the field size
(`vekn-api/doc/archon_approve.php`, the `switch` on the placement field), so the
flag is the only thing that distinguishes a disqualified player from a genuine
last place.

`vekn_tournament_sync.py` reads `pos` and nothing else — `is_finalist` is a
`pos in ("1".."5")` test and there is no mention of `dq` or `wd` anywhere in the
file. So a disqualified or withdrawn player arrives as an ordinary competitor:
`Standing.disqualified` is never set, and neither is the player-state half of the
DQ signal, so nothing downstream can recover it.

What that costs, given the row is scored rather than zeroed:

- the participation rating points a DQ forfeits are kept;
- league scoring counts them, since it skips on the flag;
- `compute_final_standings` gives them a real placement instead of the tail;
- the standings screen renders them as a placed competitor.

**This is the exact inverse of the push bug fixed in "Report the winner vekn.net
crowns at position 1".** That commit made us *send* `DQ`/`WD` correctly. We still
ignore them coming back, so an event we push and later re-import loses the very
distinction we just started reporting.

## Three sort keys for one sheet

The engine's `sort_by_rank` in `engine/src/tournament/standings.rs` orders on six
keys: excluded-last (`disqualified || non_competing`), then GW, VP, TP, toss, and
`user_uid` as a terminal tiebreak — its own comment states that last key exists so
players tied on everything do not come out in arbitrary order.

- `vekn_tournament_sync.py` sorts on five: it drops the excluded-last key.
- `archon_import.py` sorts on four: it drops the excluded-last key *and* the
  terminal tiebreak.

Neither importer parks an excluded row last, and the archon path can order tied
rows differently from the engine on the same data.

## Scope note

The archon-file importer also crowns the top preliminary seat as `winner` when no
final was played. That is **not** part of this line — it is folded into the
no-final Rules Director line, because `wiki/tournaments.md` deliberately allows a
no-final *import* to carry a winner and the ruling decides which way it goes.
