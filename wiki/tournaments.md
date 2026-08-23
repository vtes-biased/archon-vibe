# Tournaments — implementation

How the app implements [the VEKN tournament rules](domain/tournament-rules.md) and
[the Judge's Guide](domain/judging.md). Those pages state the rules; this one
states what the code does, including where it knowingly differs.

All state transitions run through the shared Rust engine, so browser (WASM) and
server (PyO3) behave identically.

## Configuration

| Setting | Values | Notes |
|---|---|---|
| Format | Standard, V5, Limited | V5 has its own decklist validation; Limited has no deck check, so draft events run as Limited |
| Rank | Standard, National, Continental | National and Continental earn the rating coefficient bonus and are engine-blocked from proxies and multideck, at create and at config edit |
| Proxies | yes/no | Standard rank only |
| Multideck | yes/no | Standard rank only |
| Decklist required | yes/no | organizer choice |
| Online | yes/no | the venue URL is the meeting place |
| `max_rounds` | int, 0 = uncapped | per-player round cap |
| `max_players` | int, 0 = none | **soft** cap, advisory for venue capacity: the UI warns past it, the engine never blocks, and there is no waitlist |
| `open_rounds` | bool | the non-VEKN house format, below |
| `self_organized_rounds` | bool | players seat their own pods |
| `standings_mode` | Private / Cutoff / Top 10 / Public | display default during play |
| `decklists_mode` | Winner / Finalists / All | applied after finish |
| `round_time`, `finals_time` | seconds; `round_time` 0 = untimed, `finals_time` 0 = use `round_time` | the shared timer |
| `table_rooms` | named rooms over table ranges | labels in seating, print and player views |

**Ranking eligibility** — the engine's `ranking_eligibility` is the single
predicate behind the rating inclusion filter, the ranked/unranked badge and the
RtP column: at least 8 players who played **and** a final — a finals table or a
named winner, which is a wider test than the `final_played` the rating bonus and
the tournament-win GW are gated on ([hazards](hazards.md)) — never for
open-rounds or self-organized events, and never for a row with no play data at all
(`no_results` — an archival record carries a winner but nothing that was played).

**Two counts, two questions.** `players_with_rounds` answers *who played* — seats
across rounds and finals, or, on a rounds-less import, standings rows carrying a
score. It decides eligibility and who earns a rating entry.
`attested_player_count` answers *how big the field was*, for the rating
coefficient and the win floors, and takes the whole result sheet including seats
that scored nothing. It is a precedence, never a maximum: our own play data, then
`reported_player_count`, then the standings length. Both are exported over PyO3
and WASM; nothing re-derives them.

**The Hall of Fame counts wins on its own predicate**, which disagrees with
`ranking_eligibility` by design — unifying them would silently rewrite
membership. Five wins make a member, and a win counts when the event would have
qualified for the TWDA *and* the winning deck is on record: finished and not
soft-deleted, not online, not open-rounds or self-organized, not Limited, a
`winner` set, at least `TWDA_MIN_PLAYERS` by `attested_player_count`, and a live
`DeckObject` for that winner on that tournament. The floor is the submission
floor of 10, not the rating floor of 8: the Hall of Fame is defined by deck
submission, so it inherits the threshold that governs submission. One exception —
an archive entry that never carried a player count and holds no play data of its
own (`no_results`) clears the floor anyway, because the archive accepting the
entry is itself the attestation, and gating on the blank costs five genuine
members over a data gap. An event whose result sheet we hold answers the question
itself and is held to the answer.

The rankings page states that criterion under its Hall of Fame tab, and a member's
profile lists the wins behind their count alongside their decklists on record, so
the number is auditable rather than asserted. A player's own profile also gathers
the events they won with no decklist of theirs attached — the same pair the
tournament page nudges on, and deliberately not the Hall of Fame predicate
inverted, which stays server-side.

The criterion is the owner's to set: the VEKN rules define no Hall of Fame. Ours
restates `vekn.fr`'s "five IRL wins posted to the forum" in terms that survive
the vekn.net decommission, and it reads the same for both corpora, differing only
in the evidence each supplies. `User.wins` is server-computed and
member-projected; no `hall_of_fame` flag is ever stored, because rule 8.6 lets a
result be invalidated and a stamped badge would outlive the correction.

`UpdateConfig` is available in **any** state — mid-event typo fixes matter — with
targeted locks instead of a state gate: `open_rounds`/`max_rounds` lock once rounds
exist, and `rank`/`format`/`start` freeze once the event is published to VEKN,
because the calendar create is write-once and an edit would silently diverge from
vekn.net ([vekn](vekn.md)).

**No Grand Prix rank, deliberately.** A Grand Prix runs as a **league** — with or
without GP scoring — because outside the multideck and proxy prohibitions
(tournament rules §3.1.5, §4.5) it differs from an ordinary tournament in nothing
the app models, and a rank value earning only two prohibitions is not worth the
category. Those two prohibitions are therefore left to organizer opt-in on a GP.
Revisit if a Grand Prix ever acquires real structural differences.

**Card-set restrictions (§6.1.1) and the Restricted format (§7.9) are not
modelled.** Such an event is entered as Limited, which is close enough in practice
and already carries no deck check. The cost is that the rules' exclusion of
set-restricted results from ratings is not applied automatically.

## State machine

```
Planned ──open──> Registration ──close──> Waiting ⇄ Playing ──finish──> Finished
```

| State | What it means | Key actions |
|---|---|---|
| `Planned` | initial | OpenRegistration |
| `Registration` | players register/unregister | Register, AddPlayer, CloseRegistration, CancelRegistration |
| `Waiting` | between rounds, check-in active | CheckIn, CheckInAll, StartRound, StartFinals, FinishTournament, ReopenRegistration |
| `Playing` | round in progress | SetScore, Override, FinishRound, CancelRound, seating edits |
| `Finished` | complete | ReopenTournament, organizer SetScore/Override, deck uploads |

`UpdateConfig`, `ReportPromos` and Delete are available in any state.
`SetScore`/`Override`/`Unoverride` are open to players only during `Playing`, and
to organizers whenever rounds exist — Waiting, Playing or Finished — with standings
recomputed after every edit. Delete is plain REST, not an engine event, gated only
on the VEKN footprint: blocked once `external_ids.vekn` or `vekn_pushed_at` is set,
since deleting would orphan the vekn.net record. Deleting a `Finished` tournament
triggers a ratings recompute for its players.

## Player states

| State | Meaning | Finals-eligible |
|---|---|---|
| `Registered` | signed up | — |
| `Checked-in` | present and available | — |
| `Playing` | seated at a live table | — |
| `Completed` | hit the per-player `max_rounds` cap; done with prelims | **yes** |
| `Finished` | withdrew, dropped, or the event ended | no |
| `Disqualified` | DQ sanction active | no |

`non_competing` is a flag rather than a state, implementing the Judge's Guide
[proxy player](domain/judging.md#event-organization-5). The seat plays normally and
its VPs count for oust-order validation and for opponents; the player is excluded
from standings rank, rating and finals. Set by organizers via `SetNonCompeting`,
blocked once finals are seeded or the tournament is Finished. The field name avoids
collision with `Tournament.proxies`, which is proxy *cards* allowed.

**A proxy's score is displayed, not hidden — deliberately.** JG v2 §5.1.1 requires
only that their points have *no effect*, which they don't: the proxy is excluded
from rank, rating and finals. Showing the score keeps the table legible, since the
VPs are real, they were earned against real opponents, and a blanked row makes the
table look wrong. This is the opposite of the DQ treatment, where zeroing *is* the
point.

**Entering the tournament at all requires a `vekn_id`.** `Register`, `AddPlayer`
and the `CheckIn` walk-in path each reject an empty one, so an official sponsors or
links the account first. Offline play is the exception — it mints `TEMP-` ids that
go-online resolves or turns into real members ([vekn](vekn.md#push-constraints)).

Barriers to check-in: a required decklist not uploaded, a VEKN ban, a
disqualification from this event, or reaching the per-player round cap.

**The door stays open mid-round** — check-in is allowed while a round is `Playing`,
and a player never registered is enrolled by it. Checking someone in never seats
them; whether a late arrival joins a short table now or waits is the organizer's
call, taken as a separate seating action. **The app has no default and must not
decide.** A round turns `Playing` the moment it is seated, while players are still
finding seats, so an arrival in that gap can often still be seated; once play has
begun they usually wait. The same path reverses a drop-out, who returns to `Playing` if their seat
is still live — dropping out never vacates a seat, which is why Drop Out carries no
confirmation. Only `Planned` and `Registration` refuse a check-in; a `Finished`
tournament accepts one only for post-hoc correction.

**There is no "Loss".** Tournament rules §3.3 and §3.1.4 assign one for the round
to a player not seated within 15 minutes of the start, or leaving after seatings
have begun. The app models drops instead: the organizer unseats the absent player
and the table plays on at 4, which is what JG §5.1 requires anyway. The one thing
that gets lost is the **last-place TP a Loss would still award** — an unseated
player scores nothing at all. That can only matter as a tiebreak between players on
equal GW and VP, and the organizer can reach the same result with an `Override` and
a comment.

Leaving the absent player *seated* is not a workaround: oust-order validation would
read their 0 VP as an oust and credit their predator a victory point they never
earned in play, which is exactly the administrative-removal-is-not-an-oust rule
(JG §1.1.4).

## Seating

Simulated annealing, computed inside the engine's `StartRound` handler — there is
no separate seating entry point. Tables of 4–5; the impossible counts 6, 7 and 11
use staggered seatings so the sit-out rotates and everyone plays equally.

The rules require only that exact predator-prey relationships are not duplicated
between rounds, and point at the legacy Archon spreadsheet's "optimal seating
chart" for more (§3.1.2). The nine priorities the engine optimizes are that
convention, in order:

1. No repeated predator-prey relationship (**mandatory**, and the only one the
   rules themselves require)
2. No pair shares a table in all rounds
3. Available VPs equitably distributed (4- vs 5-player tables)
4. No pair shares a table more than necessary
5. No player sits in 5th seat more than once
6. No pair repeats the same relative position
7. No player repeats the same seat position
8. Starting transfers equitably distributed
9. No pair repeats the same relative position group

**Seating is seeded and value-stable.** `seating::seed_for_round(tournament_uid,
round_index)` feeds a `ChaCha8Rng`, so WASM, PyO3 and the browser compute
byte-identical seating for the same tournament and round. `StartRound` also accepts
an optional explicit `seating` (table → ordered player UIDs); the frontend extracts
the WASM-computed seating and injects it into the server POST as a safety net
against engine builds drifting, not as a correctness requirement. Engine
validation: each table 4–5 players, every checked-in player exactly once, no
duplicate UIDs across tables.

Finals seating is not computed. The physical card-drawing ritual
([rules §3.1.3](domain/tournament-rules.md#final-round-seating-313)) is recorded
through `AlterSeating`; the app does not enforce it.

## Scoring

Only VP is user-submitted, per seat. GW and TP are engine-computed to the rules in
[§3.7](domain/tournament-rules.md#scoring), in
`engine/src/tournament/scoring.rs`. TP base values by table size: 5-player
`[60, 48, 36, 24, 12]`, 4-player `[60, 48, 24, 12]`, 3-player `[60, 36, 12]`. The
rules define only the first two; the 3-player row is defensive and unreachable in
sanctioned play.

### Oust-order validation

`check_table_vps` accepts a VP sheet exactly when a game could have produced it, so
seating order matters:

1. Check the table size is 4 or 5.
2. Check the total: `sum(ceil(vp)) == table_size`. Less is insufficient — the round
   is still in progress, unless the shortfall is the one-entry Life Boon signature,
   which reads `RedirectedVp`. More is invalid. Every legal sheet satisfies this,
   because `ceil(0.5) = 1` makes a withdrawal account for its own seat exactly as a
   survivor does.
3. Decide against the results the table can actually reach. They are enumerated
   from the scoring rules — one VP per prey ousted, half for withdrawing, half for
   surviving the time limit, a full point for whoever is last standing — which
   comes to 107 sheets on four seats and 546 on five, built once and cached.

**The enumeration is there because a withdrawal leaves the table.** The older pass
walked the ring, crediting each 0-VP seat's oust to its predator, and judged what
remained; it had no way to close the ring behind a player who withdrew and read
them as a survivor still sitting there. That refused 36 of the 107 legal four-seat
sheets and 280 of the 546 five-seat ones — every one a withdrawal ending, and an
organizer needed an `Override` to enter a real result. The walk survives as
`oust_order_fault`, used only to name the seat at fault in the message.

Failure modes: **MissingVP** (a fractional VP where an oust should have given a
full point, e.g. a `[0.5, 0]` sequence), **HalfVpMismatch** (the seats a legal
sheet cannot account for; the name stays directionless because such a seat is half
a VP over as often as under), **ExcessiveTotal**, **InvalidTableSize**.

Worked example, 5-player `[2, 1, 0, 0.5, 1.5]` in seating order: seat 3 is ousted by
seat 2, seat 2 by seat 1, seat 1 by seat 5, and seats 4 and 5 take half a point each
when time is called. `[2, 0, 0.5, 0.5]` is equally legal and looks impossible until
you place the withdrawals: seat 1 ousts seat 2, seats 3 and 4 both withdraw, and
seat 1 is last standing.

### Table state

1. `Cancelled` — set by `CancelRound` on a non-last round (soft cancel).
2. Otherwise, if `override` is set → `Finished` (a judge forced it).
3. Otherwise run `check_table_vps`: insufficient total → `In Progress`; other
   validation error → `Invalid`; no error → `Finished`.

### Standings

`compute_preliminary_standings` sorts GW > VP > TP with a toss tiebreak, using
competition ranking with skips. GW and TP are **recomputed** per table from raw VPs
plus current sanctions, so an SA issued after a round was scored re-decides the GW
and re-ranks TP — the frozen seat values would otherwise go stale. The VP total
sums raw per-seat VP then subtracts the SA penalty, which may go negative; per-seat
`result.vp` stays raw for display.

**Only a `Finished` table counts**, in the standings and in
`compute_rating_vp_gw` alike. `In Progress` has no ranking to report — every seat
ties, and the TP ladder averages to the same 36 on four seats and on five, so an
unplayed round would otherwise credit its whole field 36 apiece; `Invalid` has no
valid ranking; `Cancelled` did not happen. The unit is the table, not the round: a
finished table scores as soon as it is scored, while its round is still running.

**A table's state is decided where its result changes, and never re-judged
afterwards.** `SetScore`, `Override`, `Unoverride` and `RestoreRound` set it, and
`AlterSeating` returns a re-seated round to `In Progress`; the standings pass only
reads it. Seat edits do not: a table being filled keeps the state it had, which is
why a half-seated one is never badged `Invalid` mid-build. So a
finished table stays finished however it was reached — imported history included,
which is the point: `migrate_from_archon.py` copies legacy per-seat VPs without
validating them, and re-judging on recompute would silently drop tables our checker
happens to reject.

What the pass does refresh is **per-seat GW and TP**, in `refresh_round_scoring`,
from raw VPs plus current sanctions, so a late SA cascades into the seats. On a
table that is not `Finished` it writes zeros instead: an unscored one ties every
seat, and the ladder average would otherwise stamp 36 TP apiece on anything reading
the seats rather than the standings. `Cancelled` is left untouched — `RestoreRound`
re-derives the round from those retained scores.

`tournament.standings` is **prelim-only and SA-adjusted** — finals excluded. It is
empty until some table finishes, so a live first round has rounds and no standings.
The converse is the load-bearing one: **standings with no rounds mean a round-less
VEKN import**, which carries a result sheet and no round detail, and which the
`rounds`-empty guard in `update_standings` exists to protect. That guard cannot
tell such an import from a tournament that just lost its last round, so
`CancelRound` clears the standings itself when its hard-remove empties the array —
otherwise the deleted rounds' sheet outlives them, and `players_with_rounds` reads
it as a full field that played. Keeping that one case to imports is what makes the
VEKN `rounds > 0` push guard safe.

`compute_rating_vp_gw` is the single source for the backend rating and VEKN-push
paths. It applies the same `Finished`-only rule and additionally includes finals
VP/GW; prelim
comes from the rounds when present, else from the prelim-only standings row for
round-less VEKN imports; when no `finals` object recorded the win it credits the
tournament winner a +1 GW, covering an import whose final was played but not
recorded. That credit needs a final in evidence — some row flagged a finalist — so
it stays inert both for a native no-final, which leaves `winner == ""`, and for an
importer that crowned a top seat no final produced. It returns `(0, 0)` early for DQ'd and
non-competing players.

`compute_final_standings` implements §3.7.5 placement: winner rank 1, other
finalists share rank 2, non-finalists competition-ranked from `finalist_count + 1`.
Whether a final happened is read from the per-player `finalist` flag, not from
finals seating data. It also stamps each row with `finalist_position` — 1 for the
winner, 2 for the other finalists, 0 for everyone else — and that stamp is the one
source of the rating formula's finalist argument: the backend rating, the standings
screen and league scoring all read it off the row rather than each deriving it.
When no row carries the finalist flag nothing evidences a final, so every position
is 0 — the named winner included, who still places 1st but takes no bonus for a
final that was not played.

**A scoreless sheet row is a no-show and holds no placement.** An import writes a
standings row for every name on the registration sheet, so a player who never sat
arrives at 0/0/0; ranked as a competitor they tie for a real place among the last of
the field. `compute_final_standings` stamps `no_show` on such a row and appends it
with the DQ'd and the proxies — the row and the name stay, the rank does not. The
winner and the finalists are exempt, having sat by definition, and a DQ'd row is
stored zeroed so its own flag decides first. The flag is **derived at placement, not
stored**: `compute_preliminary_standings` only ever sees players who sat at a
finished table, so the class exists solely in an imported sheet. An imported
withdrawal is not in it — it kept a score, and this app ranks a player who dropped
([vekn](vekn.md#tournaments)).

**An imported sheet arrives in the engine's own order.** Both importers sort with
`sort_standings`, the one place the six-key rule lives — excluded rows last, then
GW, VP, TP, toss, and `user_uid` as the terminal tiebreak. `compute_final_standings`
competition-ranks the sheet it is handed, so a sheet ordered any other way places
tied rows the engine never would.

`display_standings` is what a client renders, exported to WASM as
`displayStandings` and called nowhere else. It **ranks the stored sheet it is
handed** — never `compute_preliminary_standings` — because a round-less import has
no rounds to recompute from and a recompute would re-judge table states the corpus
was imported with. On top of the sheet it decides the DQ/proxy flags from the
combined signals, zeroes the DQ'd, sorts the cascade and calls
`compute_final_standings`. A final places only once the tournament is `Finished`:
until then the winner is dropped and the display stays on the preliminary ranking,
and each finalist row then carries its finals `{gw, vp, tp}` for display. Toss and
finalist are sourced apart: toss off the roster when rounds exist and off the sheet
row when they do not, finalist off the finals seating — the roster flag serves only
as the round-less fallback, where neither a finals table nor a roster toss exists.
The screen hands `compute_final_standings` that resolved row while the backend
hands it the stored sheet; the two agree because every producer writes the sheet
flag from finals membership, not because the stamp reconciles them.

Its `sanctions` argument must hold **this tournament's own** sanctions and no
others. `has_dq_sanction` matches on user and level alone — the payload carries no
`tournament_uid` to filter on — so a list gathered for player context, as
`getTournamentContextSanctions` gathers 18 months of it, zeroes a player here for a
DQ they took at another event.

## Finals

Qualification follows §3.1: top 5 by GW, VP, TP, with a random toss for ties.
Organizers must drop unavailable finalists before launching.

`finals_candidates` is the one definition of who may qualify: `Disqualified` and
`Finished` (withdrawn) players are dropped and the next-ranked qualifier promoted,
`Completed` (capped) players stay eligible, non-competing proxies never enter. A
toss computed over raw standings instead orders a top five the finals never uses,
and leaves a tie no re-run can break.

The client reads the same pool over the `finalsQualification` WASM export, which
answers who may qualify, whether a toss is still owed and whom it would touch —
the three things every finals control in the UI is drawn from.

It answers whether a final may **start**, and never whether one may be shown.
`FinishFinals` and `FinishTournament` put every non-disqualified player in
`Finished`, which empties the candidate pool, so a finished tournament always reads
`possible = false` — and a round-less VEKN import, whose finals is reconstructed
rather than played, never had two played rounds to count. The finals view therefore
branches on the stored `finals` object first and consults qualification only where
there is no final to show.

`RandomToss` orders **every** tied group inside the qualifying five, not only the
one straddling the cutoff: §3.1 resolves ties for any of the top five rankings, and
the rank is not cosmetic — §3.1.3 has the **lowest** qualifier place their name card
first. The span it orders is the top five extended over everyone tied with fifth.
A group only partly tossed by hand is re-tossed whole; a group already holding
distinct non-zero tosses is left alone. The shuffle is seeded from the tournament
uid because the client applies the event through WASM before the server replays it.

`FinishTournament` without a final sets `Finished` and preliminary standings but
sets no winner or finalist flags, so a native no-final event awards no
winner/finalist rating bonus and no winner GW. That is rules-literal — A.2 credits
a game won "including a final round victory" and A.2.1 defines a finalist as one
who advanced to a final — but vekn.net's own implementation credits a no-final top
five exactly like a final, and our VEKN imports mirror that. Owner-approved interim
position: the engine stays rules-literal, and the ranked/unranked badge makes the
outcome read as a rule rather than a bug. It holds for an **imported** winner too —
where a file or a summary names a winner but flags no finalist, every
`finalist_position` is 0, so the rating, league scoring and the standings screen
decline the bonus alike, and the +1 tournament-win GW goes with it — winner credit
for a game never played is the same invention. A finals-less league weights
participation over winners by design, so crediting one there cuts against the
format. The stance bites only where **nothing** is flagged: `vekn_tournament_sync`
stamps `finalist` on positions 1–5 whether or not a final was played, because the
upstream record does not say, so a VEKN import keeps vekn.net's answer and only a
locally crowned seat loses the credit. The question is with the Rules Director.

**A no-final finish is allowed at any size, deliberately.** §3.1.6 permits omitting
the final only below 8 players, but force majeure cuts real events short — a venue
closing, an emergency termination (JG §5.3) — and the app must be able to record
what actually happened rather than refuse it. The §3.1.6 constraint on admitting
players between rounds is likewise not enforced.

Whether such an event should then count toward rankings is the genuinely open
question, and it is on the board with the Rules Director.

The pre-finals panel deliberately carries no Start Finals button: the action bar
owns every state transition and the toss-needed warning, and finishing without a
final is a legitimate exit — a panel-level launch button would present the final
as mandatory and bypass the toss warning.

## Engine event catalog

Every business event goes through `POST /api/tournaments/{uid}/action` with body
`{type, ...payload}`. There are no per-event REST routes. Each call carries the
tournament state, the event, and an actor context — user UID, roles, organizer
status.

**State transitions** — `OpenRegistration`, `CloseRegistration`,
`CancelRegistration`, `ReopenRegistration`, `ReopenTournament`, `FinishTournament`.

**Players** — `Register` / `Unregister` (self), `AddPlayer` / `RemovePlayer`
(organizer; RemovePlayer is for a player who has not played — use `DropOut`
otherwise), `DropOut` (preserves scores), `CheckIn`, `CheckInAll`, `ResetCheckIn`,
`SetPaymentStatus`, `MarkAllPaid`, `SetNonCompeting`.

**Rounds and seating**

| Event | Notes |
|---|---|
| `StartRound` | optional `seating` for deterministic forwarding |
| `FinishRound` | any round, any order |
| `CancelRound` | the last round is hard-removed and unrecoverable, and takes the run of fully-cancelled rounds trailing behind it; any earlier round is soft-cancelled — tables set to `Cancelled`, the slot preserved, players released, restorable until the last round is cancelled |
| `RestoreRound` | un-voids a soft-cancelled non-last round: re-derives each table's state from retained scores and re-arms seated players. **All-or-nothing** — if any seated player can no longer be reinstated as saved (dropped, disqualified, or already at their cap via other rounds) the whole restore is rejected rather than silently dropping them |
| `SelfOrganizeRound` | player-authorized, not organizer-gated |
| `SwapSeats` | swap two players within a table |
| `AlterSeating` | **the submitted seating decides who is in the round** — it is diffed against the current one and players are seated and unseated to match, in one event. Positional prefix match: existing tables matched by index (results preserved same-table, reset cross-table, fresh zeros for a player joining), extra payload tables appended, each table seating 0/4/5 players (0 = empty draft workspace, dropped after rebuild). On finals it replaces seat order for the same player set |
| `SeatPlayer` / `UnseatPlayer` | one seat at a time, on the round named in the payload or the live one — not necessarily the last |
| `AddTable` / `RemoveTable` | current round |

**`AlterSeating` refuses only the structurally incoherent**: a uid that is not a
tournament player, a duplicate across the payload, a table outside 0/4/5, fewer
tables than the round has, a payload that would leave the round with no table at
all (cancel the round instead), a predator-prey repeat. It applies **no player-state
filter** — every state such a filter could bar is reachable by seating the player
and then changing their state, and `StartRound` already admits `Playing` players
into a new round for parallel online play. The editor's pool therefore offers every
tournament player not already seated in the round, each tagged with their state so
the organizer sees what they are adding.

**A live round's seating decides player state**, in one promotion and one demotion
rule, shared by `AlterSeating` and `UnseatPlayer`. Joining a live round's seating
makes a player `Playing` — `Finished` if the tournament itself is, which a
force-finish can leave holding a live round — except that a disqualified player
keeps `Disqualified`, by state or by active sanction: seating them is allowed,
un-disqualifying them as a side effect is not. Leaving the seating returns a
player to `Registered` — but only *from* `Playing`, so a player who dropped out
mid-round (drop never vacates a seat) stays
`Finished` instead of being silently reinstated into finals eligibility, and only
when they are not seated in another still-live round, so parallel rounds do not
strand each other. A round that is over is not live: correcting its record moves
seats and never player state, because a finished round has no player state it can
correctly assert.

A round slot is never removed mid-array: `deck.round` and
`standings_adjustment.round_number` are index-tagged and would be corrupted.
Removal from the tail is safe, which is why cancelling the last round sweeps the
cancelled rounds behind it: their restore is worth less than ending at zero rounds
whichever order the cancels came in, since cancel is offered only while `Playing`
and a cancelled slot left stranded in `Waiting` can never be reached again.

**Scoring** — `SetScore` (`{player_uid, vp}` per seat), `Override` (organizer forces
a table Finished, comment required), `Unoverride`.

**Finals** — `SetToss`, `RandomToss`, `StartFinals`, `FinishFinals`.

**Decks** — `UpsertDeck`, `DeleteDeck`. All deck mutations are engine `deck_ops`
side effects; there are no REST deck endpoints.

**Raffle** — `RaffleDraw` (pools AllPlayers, NonFinalists, GameWinners, NoGameWin,
NoVictoryPoint; optional `prize_promo_uid`, display-only and never written to
`promos_distributed`), `RaffleUndo`, `RaffleClear`.

`get_raffle_pool` is the one pool definition, and the organizer's picker reads it
over the `rafflePool` WASM export rather than counting eligibility itself — the
count beside each pool is the set the draw will actually shuffle. It is a query,
not a gate: an empty pool is a number the picker renders and only `RaffleDraw`
rejects.

**Promos** — `ReportPromos`, replace-the-whole-list, no state gate, since counts
are typically entered post-finish and re-entered on correction.

**Config** — `UpdateConfig`.

**Archival correction** — `SetArchivalResults` (`{winner, players, reported_player_count}`),
IC only. Replaces the roster and the winner wholesale on a Finished event we hold
no play data for, and stamps the attested field size. The gate is the data shape,
not a stored mode: it refuses whenever `players_with_rounds` is non-zero, so it can
never overwrite a real result sheet. It also refuses a row carrying a vekn.net id,
whose nightly sync would rebuild the row and silently drop the correction —
lift that once the calendar sync retires ([vekn-decommission](vekn-decommission.md)).
No `standings` payload: they are prelim-only by contract and an archival record has
no prelim, so the rows stay zeroed.

An archival row reads as one on the tournament page. The player count is shown as
*reported* from `attested_player_count` rather than the roster wherever a row holds
no play data of its own and an attestation to show — the same predicate that gates
the write, so an IC correction lands on the page whether or not the row came from
the archive. With no attestation the line is dropped entirely: the archive carried
no count on about a hundred entries, and there the field size is unknown rather
than the one seat the reconstruction holds. The *Archival* badge additionally
requires a `twda` id, since that is what its text claims — but never the id alone,
because adoption keeps it while overwriting the row with a full VEKN result set,
and the VEKN record outranks the archive from that moment on.

### Who may do what

| Action | Who |
|---|---|
| Create tournament | IC, NC, Prince |
| Register / Unregister | any authenticated member, during Registration |
| Self-organize a round | registered players, open rounds with `self_organized_rounds`, Waiting/Playing, no finals |
| Set score | players at the table during Playing; organizers whenever rounds exist |
| Deck upload | players for their own deck, organizers for any |
| Correct an archival record | IC |
| Everything else | organizers |

Enforcement is single-sourced in `engine/src/permissions.rs` and applied at both
the REST endpoint and the engine — see [access](access.md).

**Organizer eligibility is not enforced.** §1.1 bars the organizer of record and
the judges of record from playing except under the Multi-Judge System (§2.9), which
the app does not model at all. Organizers may register and play in their own event
with no warning. This is knowingly unmodelled, not an oversight — eligibility is a
human call the organizer already owns, and the six-judge structure of §2.9 has no
representation worth building.

## Open rounds

`open_rounds` marks the tournament as the non-VEKN **house format**: such events
are never pushed to VEKN and never counted toward ratings or RtP, enforced in the
push queries, the `push_tournament_event` guard and the ratings recompute filters.

The flag is **decoupled from `max_rounds`** on purpose: the VEKN-push build forces
`max_rounds` to 2–4 on every standard tournament, so `max_rounds > 0` alone cannot
distinguish a house open-rounds event from a standard one.

The per-player cap mechanics are driven by `max_rounds > 0`, independent of the
flag — a standard tournament where everyone plays every round hits its cap
naturally:

- Each player plays up to `max_rounds` rounds from a shared pool. The tournament
  keeps running new rounds for players who have not hit their cap, so total rounds
  started may exceed `max_rounds`.
- On reaching the cap a player retires to `Completed` — finals-eligible, done with
  prelims. `CheckIn` is refused; `CheckInAll` skips them.
- Deck locking becomes per-player: a player's deck locks when they hit their cap or
  their last round starts, rather than tournament-wide.
- Standings are cumulative GW > VP > TP across all rounds played, as usual.

### Self-organized rounds

Settable on any open-rounds tournament, with no online or per-player-cap
requirement. Eligibility: tournament in Waiting or Playing with no finals; exactly
4–5 distinct players in `Registered` or `Checked-in` (not `Playing`, `Completed` or
`Disqualified`), initiator included.

Trust-based — registration is the only integrity gate and collusion risk is
accepted, this being a non-VEKN house format outside the rules' seating
requirements. The engine computes single-table seating (best-effort predator-prey
on round 1, using prior rounds thereafter), moves seated players to `Playing`,
leaves unseated `Registered` players untouched, and stamps the table
`organized_by: <initiator_uid>` for audit. Never for finals, never VEKN-pushed.

Organizer oversight is unchanged: `FinishRound` closes any round in any order,
`CancelRound`/`RestoreRound` void and un-void, `Override` voids a table result.

`StartRound` withdraws `Registered` no-shows only on round 1 of a standard
tournament; rounds 2+ and open rounds leave them untouched, and a zero-rounds
no-show is reinstatable by `CheckIn` between rounds, or onto a live table by
`SeatPlayer` or the seating editor.

## Sanctions

Sanctions are their own synced object type. The levels, their durations and who may
issue them are [domain](domain/judging.md); the app's visibility rules are here.

| Level | Where it shows |
|---|---|
| Caution | only inside its own tournament — never on member pages or in other events, for anyone including IC and Ethics |
| Warning, Standings Adjustment, Disqualification | member detail page, members list, and other tournaments' context, for **18 months** from issuance |
| Suspension, Probation | membership-level, always visible; a permanent ban stays visible past 18 months |

The filtering is a **display rule**: all sanction records sync to every member's
client at member level. IC and Ethics see every level on every surface.

Expired sanctions are soft-deleted daily after 18 months and hard-deleted 30 days
later, so a mistaken organizer delete stays IC-recoverable in that window.

| Action | Caution / Warning / SA / DQ | Suspension / Probation |
|---|---|---|
| Issue | IC, Ethics, or an organizer of the tournament | IC, Ethics |
| Lift | IC, Rulemonger, the NC of the tournament's country; a league organizer for a DQ in their league event | IC (Ethics to modify) |
| Edit fields | IC, Ethics | IC, Ethics |
| Delete (soft) | IC, Ethics — plus the tournament's own organizer **while the event is not Finished**, for mistake correction by delete-and-reissue (organizers cannot edit) | IC, Ethics |

The category, subcategory, baseline and escalation reference is generated from
`engine/src/sanctions.rs` and served at `GET /sanctions/reference`. The app
suggests a level by category and warns when issuing below an existing one.

**A DQ is issued as one sanction, and that satisfies §1.1.4.** The rule's "a DQ
always includes a Warning" is a paper-records instruction: on paper a DQ is a
table ruling that leaves no lasting trace, so the Warning is what the judge files
to make it durable and reportable. Here a DQ *is* a first-class recorded
sanction, carrying the same 18-month cross-tournament visibility as a Warning and
outranking it on the escalation ladder — so a companion Warning would add a
weaker duplicate of a record that already exists, not a missing one. Reading the
rule literally and issuing both is the mistake to avoid.

### Standings Adjustment mechanics

The −1 VP lands on the player's standings total for one round. **Per-seat VP is
untouched** — raw `seat.result.vp` stays valid, so the VP sum still equals the table
size and the oust order still parses. The penalty lives only on the standings
total, may drive it negative, and is never carried to another round.

**GW and TP cascade** as §1.1.3 requires: standings recompute GW and TP per table
from raw VPs plus current sanctions rather than trusting the frozen seat values.

**Round targeting.** The effective round is the highest round index in which the
player sits at a **finished** table — the same tables the standings score, so the
−1 VP and its GW/TP cascade land together instead of the penalty resting on a round
no cascade reaches. A live round therefore holds no SA: the penalty appears once
that round finishes. Finals are **included**, participating as round index
`len(rounds)` — the same sentinel `SetScore` uses, accepted by the backend once a
finals table exists. The stored `round_number` is the fixed issue-time record of
the game the judge ruled on; the engine honors it when the player was seated in
that round and otherwise redirects to their most-recently-seated round, so an SA
referencing a round they sat out lands on a game they actually played. A player who
has not yet played contributes nothing until they do. The UI auto-computes the
round; there is no free round picker, so a later round starting cannot migrate an
existing SA.

> **Diverges from the rules, deliberately.** JG v2 §1.1.3's third case — an SA
> issued **before round 1 pairings are announced** applies to round 1 — is not
> implemented, and will not be: the backend requires an existing round, so the
> judge issues the SA once round 1 is seated instead. The outcome is identical,
> because round targeting picks the highest round the player is seated in and
> that is round 1. Building it would mean a penalty parked on a round that does
> not exist yet — the one case where the guide does that — with a migration path
> to write and a state to reason about, to save a judge a few minutes' wait.

**Finals-round SA** penalizes the finals result rather than the preliminary totals:
prelim standings exclude finals-round SAs from their VP penalty, and the −1 VP
instead applies to the finals GW derivation — it can flip who wins the tournament —
and to the rating VP total, which includes finals VP. Every standings recompute
re-scores a finished finals table from raw VPs plus current sanctions and re-derives
the winner, so a finals SA issued or lifted after the fact still lands. If
`CancelFinals` later nulls the finals, a finals-targeted SA gracefully redirects to
the player's last prelim round and re-lands on the finals when a new final seats
them.

`resolve_sa_effective_rounds` (`engine/src/tournament/sanctions.rs`) resolves each
active SA to its effective round once per compute and feeds both the per-table
GW/TP cascade and the VP total, so the two can never disagree. Both backend and
frontend read `tournament.standings` rather than re-deriving SA from raw seats.

Issuing, lifting, editing or deleting an SA or a DQ tied to a tournament immediately
triggers a standings recompute, and the updated tournament is broadcast over SSE.

**Offline sanction management** — event-level sanctions of a device-locked
tournament are created and deleted offline, written to IndexedDB, with the client
mirroring the server's side effects: DQ player-state flips, including the playable
restore, and a standings recompute through the same shared Rust. At go-online the
sanctions ride the snapshot, the server asserts DQ states inside the locked
transaction and runs one authoritative recompute. VEKN-wide suspension and probation
stay online-only.

### Disqualification

The DQ signal is `player.state == "Disqualified"` **or** an active
`disqualification` sanction — either is sufficient, and every consumer must check
the combined signal.

- **Standings row**: sorted last, flagged disqualified, VP/GW/TP shown as 0
  (forfeited), no numeric rank. Opponents keep everything they earned at the table.
  §1.1.4 says the player is "removed from standings entirely" and the rest move up;
  showing a zeroed unranked row achieves the second half while keeping the record
  visible.
- **Rating**: no points at all — no participation base, no finalist bonus, no
  rating-history entry.
- **Player count**: DQ'd players stay **included** in the rating coefficient's
  player count, per A.2.
- **Reversibility**: lifting or deleting an active DQ restores the player to a
  playable state — `Playing` if still seated at a live table, `Checked-in`
  otherwise, `Finished` only on a finished tournament. A fat-fingered DQ is fully
  reversible, so it needs no confirmation.

## Data model

Canonical shapes are in `frontend/src/lib/types.ts` and `backend/src/models.py`.
The non-obvious structure:

- `rounds: Table[][]` — outer index is the round, inner the tables in it. `finals`
  is a separate field, **not** a round, except where the SA sentinel index
  `len(rounds)` addresses it.
- `Table` carries `seating: Seat[]`, a derived `state`, an optional `override`, and
  an optional `organized_by`.
- `Score = {gw, vp, tp}` per seat; only `vp` is submitted.
- `finals.seed_order` holds player **user_uids** — easily missed in any per-player
  UID remap.
- `reported_player_count` — externally attested field size, `0` meaning no
  attestation. Written only where nothing else answers, and read only there too,
  so it can never contradict a roster we hold. Never named `player_count`: that
  key is already taken ([hazards](hazards.md)).

## Where the code lives

- `engine/src/tournament/` — event processing, state machine, scoring, standings,
  raffle. Entry point `process_tournament_event(tournament, event, actor,
  sanctions, decks) → {tournament, deck_ops}`.
- `engine/src/seating/` — the seating algorithm.
- `backend/src/routes/tournaments.py` — endpoints, offline lifecycle, push hooks.
- `frontend/src/lib/engine.ts` — the WASM wrapper; `api.ts` — `tournamentAction()`
  and the optimistic path.
