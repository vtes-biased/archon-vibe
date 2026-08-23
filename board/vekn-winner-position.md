# The wrong winner on vekn.net — context

Doc-impact: [`wiki/vekn.md`](../wiki/vekn.md) archondata format section, and the
placement-consumer list under "Consumers that must move together" in
[`wiki/hazards.md`](../wiki/hazards.md).

## What goes wrong

The first field of each archondata player record is the **final** placement.
vekn.net stores it verbatim as `veknparticipant.pos` and reads position 1 as the
tournament winner — the same contract our own inbound sync relies on. Its rating
batch then recomputes every player's rating points from that position, discarding
the ones we send.

We fill that field with the player's index in `tournament.standings`. Those
standings are preliminary-only: they aggregate `rounds` and never the finals table,
so the finals result exists nowhere in them. The finals winner is carried by
`tournament.winner` alone, and the push never reads it. Whenever the final is won
from anything but the top seat, vekn.net crowns the top seed and awards them the
winner's rating bonus.

The engine already holds the correct rule and bands placements the way the format
wants — winner 1, the other finalists 2, the rest from 6. The ratings path uses it.
The push computes it too, for the rating-points field, and then ignores it for the
placement.

Two traps in the fix: that helper drops disqualified, proxy and no-show rows, which
the current loop still emits, and vekn.net renders rows in the order it receives
them, so the finalists have to come first.

## Measured evidence

Event 13385, *Fee Stake: Jyväskylä 9*, 15 August 2026, 2R+F. Ari-Pekka Alestalo
won the final with 3 VP from the fifth seat. Lasse Pöyry led the preliminaries and
took 0 VP in the final. What vekn.net holds, in our push order:

| pushed | player | GW | VP | TP | final VP | rating |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Lasse Pöyry | 1 | 5.0 | 114 | 0.0 | 116 |
| 2 | Pasi Karjalainen | 1 | 5.0 | 114 | 2.0 | 66 |
| 3 | Reetta Raitanen | 1 | 5.0 | 108 | 0.0 | 58 |
| 4 | Antero Hakala | 1 | 3.0 | 88 | 0.0 | 50 |
| 5 | Ari-Pekka Alestalo | 0 | 2.0 | 72 | 3.0 | 50 |
| 6 | Jiri Salo | 0 | 2.0 | 72 | 0.0 | 13 |

The order is exactly GW, then VP, then TP — the preliminary sort. The winner's 116
rating points sit on the wrong row.

## What the code fix cannot reach

**13385 itself.** The upload endpoint refuses a second submission once an archon
file is stored, and offers no overwrite. Correcting the record needs the
Rulemonger's own access on vekn.net. Once the position is right, the rating batch
recomputes the points from it, so the ratings heal on their own.

**Events already pushed with the same fault.** Any finished, pushed event whose
winner is not the first row of its standings:

```sql
SELECT "full"->>'uid', "full"->>'name', "full"->'external_ids'->>'vekn'
FROM objects WHERE type='tournament' AND deleted_at IS NULL
  AND "full"->>'state'='Finished' AND "full"->>'vekn_pushed_at' IS NOT NULL
  AND "full"->>'winner' IS DISTINCT FROM ("full"->'standings'->0->>'user_uid');
```

Each hit needs the same manual correction on vekn.net.
