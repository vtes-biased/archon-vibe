# Judges guide v2 — announcement to Princes & judges (draft)

Placeholder to fill before sending: **[DATE]** (effective date).

Sources: `reference/judges-guide.md` (2004 guide, previous version) vs
`reference/judges-guide-v2.md` (new guide, shipped in-app at
`frontend/src/lib/help-content/judges-guide.md`). Engine support for the new
penalty levels: `engine/src/sanctions.rs`, `engine/src/tournament/standings.rs`.

---

**Subject: The Judges' Guide is retired — the new Tournament Conduct & Infraction Guide takes effect on [DATE]**

Dear Princes and judges,

On **[DATE]**, the VEKN Judges' Guide — essentially unchanged since 2004 — is
replaced by the new **Tournament Conduct & Infraction Guide**. It is a complete
rewrite: new penalty system, reorganized infractions, and detailed procedures
for the situations the old guide left to improvisation. You can read it in full
in the Archon app (Help → Rules), with deep links you can share to the exact
paragraph. The English version is authoritative.

Here is what changes in practice.

## The Game Loss is gone

The biggest change: the **Game Loss penalty no longer exists**. Its replacement
is the **Standings Adjustment**: a formally tracked **–1 VP** penalty.

- The game itself is left untouched — no more awarding pool or VPs to the
  predator, no more "recorded as a loss to all active players". The table keeps
  playing normally; the penalty hits the offender's score, not the game.
- The –1 VP applies to the current game (or, between rounds, retroactively to
  the previous one). Since the Game Win goes to the highest VP total, a
  Standings Adjustment can change who gets the GW, and Tournament Points follow.
- In the new Archon, you just record the Standings Adjustment — the –1 VP, GW
  and TP recalculations are applied automatically.

## A gentler escalation ladder — but per event only

The old rule was one step up per repeat: Caution → Warning → Game Loss → DQ.
The new ladder repeats each level once before escalating:

**Caution → Caution → Warning → Warning → Standings Adjustment → Standings
Adjustment → Disqualification**

Escalation now explicitly resets between tournaments. Penalties from previous
events stay visible to judges as context (patterns, credibility, intent) but
never advance the ladder at your event.

## Disqualification: one kind, with a real procedure

"Disqualification without prize" no longer exists. A DQ removes the player from
the event and from the standings; prizes follow the corrected standings, and
everyone below moves up. The guide now spells out what the old one never did —
what happens to the table when a player is disqualified mid-game:

- **A DQ is not an oust**: no VP and no pool for the predator.
- The player's cards are removed, their predator and prey become adjacent, and
  the game continues.
- Restarting the table is allowed but strongly discouraged (early five-player
  games only, with specific rules for finals).

DQs for intentional acts must be reported to the VEKN Ethics Committee;
accumulation DQs need not be.

## Infractions are reorganized — and there are new ones

Infractions now fall into three groups: **Procedural Errors** (gameplay
mistakes), **Tournament Errors** (decks, pace, materials), and
**Unsportsmanlike Conduct** (behavior and everything intentional). The familiar
ones are all still there — deck problems, slow play, marked cards, stalling,
cheating, bribery, fraud, collusion. Worth learning:

- **Failure to Maintain Game State** — a player who clearly *notices* an
  ongoing rule violation and stays silent now takes a Standings Adjustment.
  Game state is everyone's responsibility.
- **Failure to Play to Win** — the play-to-win obligation is now written down
  as a priority ladder (game win, then max VPs, then survive to time for the
  half point), with explicit rules for which deals are legal and concrete
  examples (self-ousting with no hope left, conceding when your GW is secured).
- **Outside Assistance** — strategic advice from anyone not seated at the game,
  in either direction, including notes prepared before the round.
- **Public Information Miscommunication** and **Obscuring Game State** — giving
  wrong pool/blood answers, or keeping a layout nobody can read.
- **Insufficient Shuffling**, **Bribery *and Wagering*** (spectator bets
  included), **Theft of Tournament Material**, **Aggressive Behaviour**,
  **Health & Safety Disruption**, and **Rage-Quitting** each get their own
  entry and penalty.
- **Stalling** is now an outright **Disqualification** (it was a Game Loss).
  The guide treats deliberate clock abuse as cheating.

The appendix ends with a one-page penalty summary table — print it or keep the
app open.

## Procedures judges no longer have to invent

The new guide codifies the judgment calls the old one left open:

- **Time extensions and clock stops** — when to grant them, how much time for
  what kind of intervention, how they stack, and a default cap.
- **Roll-backs and partial corrections** — a roll-back must be complete and
  sequential or not happen at all; when it can't, a partial game-state
  correction removes the illegal element and nothing else. Head Judge approval
  required.
- **Assessing intent** — assume good faith, judge patterns rather than isolated
  actions, never punish suboptimal play. VTES is political by design.
- **Linked infractions** — one error, several matching infractions: apply only
  the most severe.
- **No retroactive penalties** once an event is concluded and approved (Ethics
  Committee cases excepted).

## For organizers

The Event Organization section adds a **proxy player** procedure (a tournament
official fills a vacant seat at large events — plays to win, scores nothing), a
full **force majeure** protocol (when to terminate, how to score a terminated
event, hostile-venue situations), and a **recommended supplies** checklist for
your judge kit (spare sleeves, neutral proxy cards, timers, printed rules).

## What does not change

Judge ranks (Rulemonger, Judge, Judgekin) and the judge tests are unaffected —
they are simply no longer part of this document. And the philosophy stays the
same: penalties exist to teach and protect fair play, not to punish.

Please read the new guide before your next event — the penalty summary in the
appendix is the fastest way in. Questions or feedback: open the **Help** page
in the app and use the **Send feedback** button.

Thank you for keeping our games fair,

The VEKN team
