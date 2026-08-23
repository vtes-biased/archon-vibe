> Elaborated context for a line in `BOARD.md`. Deleted with the line.

# Three answers to "was this player a finalist?"

Doc-impact: the finalist-sourcing rule in
[`wiki/tournaments.md`](../wiki/tournaments.md) (the `display_standings`
paragraph), and the hand-written-twins paragraph under "Consumers that must move
together" in [`wiki/hazards.md`](../wiki/hazards.md), which shrinks to one source.

## The rule already exists

`wiki/tournaments.md` states it: finalist is sourced **off the finals seating, and
the roster flag serves only as the round-less fallback, where neither a finals
table nor a roster toss exists**. This is not an open design question — it is a
recorded decision that two of the three implementations do not follow.

## The three implementations

All three feed the same engine formula, `compute_rating_points(vp, gw, fp,
player_count, rank)`, which takes the finalist position as a *parameter* — so every
caller derives it itself.

| where | how it decides | against the rule |
| --- | --- | --- |
| `backend/src/ratings.py` `_finalist_position` | finals seating, else the sheet's `finalist` flag | correct — it is the rule |
| `frontend/src/lib/tournament-utils.ts` `getRatingPts` | finals seating only | **no round-less fallback** |
| `engine/src/league.rs` (inline, RTP branch) | the `finalist` flag only | **never reads finals seating** |

Each shortcut is wrong on exactly the shape the other one handles.

## Measured

The frontend gap, run against `_finalist_position` on the shape
`vekn_tournament_sync.py` produces for a summary-only import (finalist flags on the
top five, no `finals` object, because the finals VPs summed to zero):

| player | backend | frontend |
| --- | --- | --- |
| winner | 1 | 1 |
| runner-up | 2 | **0** |
| third finalist | 2 | **0** |
| non-finalist | 0 | 0 |

So the standings screen shows those runners-up a rating short of the finalist
bonus — `30 · coefficient` — that their own rating page gives them. That also
breaks the standing rule in `wiki/hazards.md`: a frontend figure the backend also
computes must call the same binding with the same inputs.

The league gap is the mirror, reached whenever a winner's standing carries no
finalist flag — the legacy ETL takes `winner` and `finals_seeds` from independent
fields in the old record, so it can produce exactly that. The backend gives such a
winner 1 and the full `90 · coefficient` bonus; league gives 0, scoring the winner
as an also-ran, against league's own comment claiming it matches the global rating.

## Shape of the fix

The natural home is the thing that already single-sources placement: have
`compute_final_standings` stamp the finalist position on the rows it returns,
beside the `rank` and `no_show` it already stamps. Then league reads it off the map
it already builds, the frontend off the `displayStandings` rows it already has, and
`ratings.py` off `_final_standings`. Three derivations die.

**This changes league scores** for any league holding an event whose winner carries
no finalist flag — that winner stops being scored as an also-ran. The number moving
is the point of the fix, but it will be visible.
