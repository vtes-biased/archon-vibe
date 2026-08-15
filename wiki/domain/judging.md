# Judging and penalties

The penalty system the app records. Source: `reference/judges-guide-v2.md`
(Tournament Conduct & Infraction Guide, the current guide), section numbers cited
inline. `reference/judges-guide.md` is the 2004 v1 guide, kept for historical
rulings and served in-app; v2 is what the app models.

## Philosophy

Penalties exist **primarily to teach** (§1). The judge's first responsibility is
to help the player understand what went wrong; the penalty reinforces the lesson
and deters repeats. Their function is corrective and preventative, not punitive.
Judges respond to issues rather than policing for them, though they may act
proactively outside active play — registration, deck checks, card legality.

Only the Head Judge may diverge from the guide, and only in extraordinary
circumstances the guide does not cover. Round number, player skill or age, a wish
to be lenient, and judge experience are explicitly **not** grounds for deviation
(§1).

Once a tournament has concluded and been approved, infractions not ruled on during
the event are **not** subject to retroactive penalties, except for proven
intentional misconduct handled by the Ethics Committee (§1.2).

## The four penalty levels (§1.1)

**Caution** (§1.1.1) — the lightest penalty, for very minor infractions that are
immediately fixable, cause no lasting disruption and give no strategic advantage.
Purely verbal, and must include what rule was violated, the correct procedure, and
what happens if it recurs. **Cautions need not be recorded in the official penalty
system**, but the floor judge should tell the Head Judge so patterns can be
noticed.

**Warning** (§1.1.2) — formally tracked, issued when incorrect play or a
procedural problem needs time to fix, or when a minor issue has escalated to
affect the game state. Must be communicated clearly, explained, reported to the
Head Judge, and **submitted to the VEKN Penalty Database as a permanent record**.

**Standings Adjustment** (§1.1.3) — severe, formally tracked, for an infraction
warranting more than a Warning but not removal from the event. Rather than
altering the game state it imposes a **−1 VP** tournament-level consequence,
preserving the integrity of the multiplayer game.

Which game the −1 VP lands on:

| When the SA is issued | Which game it applies to |
|---|---|
| during an ongoing game | that same game |
| between preliminary rounds, or after the last preliminary round | the **previous** game the player played, applied retroactively — there is no guarantee they will play the upcoming round |
| **before round 1 pairings are announced** | **round 1** |

An SA does not directly change GWs or TPs, but because a GW goes to the player
with the highest VP total at the table, −1 VP **may change who receives the GW**,
and any change in VP status changes the TPs awarded for that round under the
standard tournament rules.

> §1.1.3 Example 1 — a player who wins 3–2 and takes −1 VP finishes on 2. If that
> creates a tie for highest VP the result is a 2–2 tie with no GW, and TPs follow
> the tie rules.
>
> §1.1.3 Example 2 — Player A sweeps a 5-player table for 5 VP and the GW. Player
> E, on 0 VP, took an SA during the game and is now on −1 VP. A receives the full
> 60 TP. The three players tied for 2nd–4th receive (48 + 36 + 24) / 3 = 36 TP
> each. The penalized player, now alone in 5th, receives 12 TP.

SAs always affect standings for the event and may influence qualification, seeding
or placement.

**Disqualification** (§1.1.4) — the most serious tournament penalty. **A DQ always
includes a Warning** and removes the player from the event. Grounds: deliberate
cheating, threats to competitive integrity, serious or repeated unsportsmanlike
conduct, obstructive or abusive behavior, or actions that endanger others.

- The player loses their current round and is dropped from the tournament.
- **The disqualified player is removed from standings entirely; remaining players
  move up in rank** and receive prizes or qualifications associated with their new
  placement.
- Prizes are reassigned by final standings. An unawarded prize passes to the next
  eligible player; an already-awarded one may be reclaimed where appropriate.
  Participation items already given to everyone are not reclaimed.
- Proof is not required — the Head Judge need only conclude that enough
  information exists to judge the event's integrity at risk.
- DQs must be submitted to the penalty database. Those arising from **intentional**
  acts compromising competitive integrity or player safety must be **escalated to
  the VEKN Ethics Committee**; DQs used purely as a tournament control measure need
  no escalation.
- A DQ may also apply to non-players — spectators, staff.

**Game state after a DQ**: the player's turn ends immediately and all their
material leaves the table. **A DQ is not an oust: the predator gains no victory
point and no pool**, because it is an administrative removal, not a game result.
The predator and prey of the removed player become adjacent and play continues as
if the DQ'd player had never sat between them. Restarting a table is allowed but
strongly discouraged, and only in five-player games where the DQ occurred very
early; a restarted preliminary table is reseated as a four-player table, while a
restarted **final** must still be five players, so the next-highest-ranked player
present is seated and the whole pre-final seating ritual is run again.

### Escalation (§1.2.1)

Repeat offenses of the same infraction escalate along:

**Warning → Warning → Standings Adjustment → Standings Adjustment →
Disqualification**

An infraction whose baseline is Caution runs Caution, Caution, Warning, Warning,
Standings Adjustment, and so on. One whose baseline is Warning runs Warning,
Warning, SA, SA, Disqualification. A player disqualified purely by this escalation
keeps prizes already awarded and stays eligible for further prizes earned in the
same tournament.

## Infractions and baselines

The categories the app tracks per sanction, with the baseline penalty from the
guide's Appendix — Penalty Summary. The canonical machine-readable copy is
`engine/src/sanctions.rs`, served at `GET /sanctions/reference`.

**Procedural Errors (§2)**

| Infraction | Baseline |
|---|---|
| Missed Mandatory Effect | Caution (minor) / Warning (major) |
| Card Access Error | Caution |
| Game Rule Violation | Caution (minor) / Warning (major) |
| Failure to Maintain Game State | Standings Adjustment |

**Tournament Errors (§3)**

| Infraction | Baseline |
|---|---|
| Illegal Decklist | Warning (minor) / Standings Adjustment (major) |
| Illegal Main Deck (legal decklist) | Standings Adjustment |
| Illegal Main Deck (no decklist used) | Standings Adjustment |
| Outside Assistance | Standings Adjustment |
| Slow Play | Caution |
| Limited Procedure Violation | Caution |
| Public Information Miscommunication | Warning |
| Obscuring Game State | Caution |
| Marked Cards | Warning (minor) / Standings Adjustment (patterned) |
| Insufficient Shuffling | Warning |

**Unsportsmanlike Conduct (§4)**

| Infraction | Baseline |
|---|---|
| Minor | Warning |
| Major | Standings Adjustment |
| Aggressive Behaviour | Disqualification |
| Bribery and Wagering | Disqualification |
| Theft of Tournament Material | Disqualification |
| Stalling | Disqualification |
| Cheating | Disqualification |
| Fraud | Disqualification |
| Collusion | Disqualification |
| Health & Safety Disruption | Warning → removal from the venue if uncorrected |
| Rage-Quitting | Disqualification |
| Failure to Play to Win | Warning (minor) / Standings Adjustment (major) |

Game Loss is not a penalty in this guide.

## Event organization (§5)

**Unexpected drop** (§5.1) — a player leaves and cannot continue:

- during seating for a 5-player table → convert it to a 4-player table;
- during seating for a 4-player table → re-seat players to form legal table sizes,
  following tournament rules §3.1.2;
- at a large event not using the multi-judge system, if a player drops at a
  four-player table **after all other tables have already begun**, the seat must
  be filled by a tournament official as a **proxy player**, using a deck chosen at
  random from decks brought by staff;
- if the drop leaves the event unable to form legal tables, **the event
  immediately becomes unsanctioned**; adjustments between rounds — such as the
  judge joining as a player — may restore sanctioning;
- if that happens before the first round, the event is unsanctioned and no
  official prize support should be distributed;
- if it happens during the tournament, **prize support may still be distributed
  normally**. Submit the report as usual with a note; the event appears as
  unsanctioned and does not affect player ratings.

**Proxy player** (§5.1.1) — a tournament official temporarily occupying a vacant
seat to preserve the required table size. **Not a participant**: they do not
compete for standings, ratings or prizes, and their role is purely procedural.

They must play to win in good faith, avoid bias, keep a consistent pace, refrain
from using knowledge of players or standings unavailable in-game, and follow all
rules as a normal player. Their deck must be functional and reasonably
competitive, legal for the format, and chosen at random from a staff pool; staff
should prepare a small pool of pre-approved decks for the purpose.

Scoring: **a proxy player does not receive victory points, game wins, or
tournament points, and any they would obtain are not recorded and have no effect
on standings.** They may still oust and be ousted, and those events affect the
game state normally — victory points arising from interactions involving the proxy
are awarded to the other players as usual, the proxy simply retaining none. Their
presence must not otherwise alter the scoring structure for the remaining players.

**Venue interference** (§5.2) — round times may be adjusted to satisfy the venue.
The event becomes unsanctioned if any round uses a time limit **shorter than two
hours and at least one table in that round ends on time being called**. A short
round in which no table reaches the limit leaves the event sanctioned. Note venue
problems in the event report.

**Force majeure and emergency termination** (§5.3) and the organizer's recommended
supplies (§5.4) are procedural and outside the app's model.

## Time extensions

If a judge takes more than a minute to make a ruling they may extend the game time
appropriately, and the extension must be clearly communicated and recorded
immediately ([tournament rules §2.8](tournament-rules.md#roles)). The guide
repeats this for Warnings and SAs whose resolution runs long (§1.1.2, §1.1.3).
