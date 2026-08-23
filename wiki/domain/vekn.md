# VEKN, the organization

The body whose records the app keeps: its structure, its ratings, its ethics
process, and the external systems the app must interoperate with. Sources cited
inline — `reference/code-of-ethics.md` (v1.5, effective 9 September 2019),
`reference/tournament-rules.md` (Appendix A for ratings), and owner interviews
where marked.

## What it is

The **Vampire: Elder Kindred Network** is the official players' organization for
VTES. It sanctions and regulates official tournaments and maintains and publishes
players' ratings and rankings (Code of Ethics, Introduction).

**Black Chantry Productions** is the publisher. In August 2018 BCP accepted a
proposal to internalize governance and administration functions from VEKN,
dissolving the VEKN Inner Circle leadership group. BCP's remit includes card
revision and publication, maintaining card rulings, errata, tournament rules and
judging guidelines, **maintaining the official player rating system**, and
providing official communication channels (Code of Ethics, Introduction).

*(Interview, owner, 2026-08-15: the app nevertheless models an "IC" role as its
global administrator tier, matching current vekn.net practice and naming rather
than the 2018 dissolution described above. Treat the app's IC as "global admin".)*

## Roles

**Princes** are volunteers promoting VTES locally, coordinating tournaments and
demonstrations. **National Coordinators** hold the same role over a broader
geography, plus responsibility for approving tournament sanctioning in their
region (Code of Ethics, Introduction).

The **Ethics Committee** considers allegations of unethical conduct, chaired by
BCP's Organized Play Coordinator. BCP designates three VEKN members to sit, plus a
fourth as alternate, with no fixed term. The National Coordinator responsible for
the region of the member under allegation gets equal participation and voting
rights for that investigation, bringing the panel to five (Code of Ethics,
Introduction).

The app additionally models Judge, Sheriff — the rank the judges guide calls
*Judgekin* — Rulemonger, Playtest Coordinator, Playtester, Ethics and DEV. These
are app-managed appointments; how they are granted is [access](../access.md), not
domain.

## Ethics sanctions

Source: `reference/code-of-ethics.md`, "Sanctions" and "Procedures".

The word "sanction" carries both senses in VEKN documents — a penalty, and
official approval of an event. Both appear in the app.

**On-site sanctions** are reserved for clear, gross violations occurring within an
event that merit more than disqualification from that single event. **Only a head
judge may issue one**, and it must be noted in the tournament report. The player is
immediately disqualified from the current event and suspended from further
sanctioned events. **The duration is 30 days and applies only to the nation in
which it was issued.** The head judge must initiate review with the Ethics
Committee **within 5 calendar days**, or the suspension lifts.

**Review** of all sanctions, whatever their origin: within 14 days of receipt;
**lifted automatically if review does not complete within 14 days**; upheld only
on a 3/5 majority; the player returns to active status if not upheld. The accused
is interviewed and may provide their own witness list. **There is no appeal
process** — the Committee's determination is final.

The three severity levels, applicable worldwide once issued:

| Level | Duration | Effect |
|---|---|---|
| **Standard suspension** | from the remainder of the original 30-day term up to **18 months from the date of the incident** | barred from sanctioned events; at the Committee's discretion may also lose all VEKN privileges including website access |
| **Probation** | **not exceeding 12 months**, and **only once in a career** | retains all privileges including play; any further violation in that term triggers a mandatory suspension, with the remaining probation term added to it |
| **Ban** | permanent | barred permanently, **removed from the VEKN Player Ratings system**, and may lose forum and website access |

**Suspended members forfeit all organizational roles or offices — Prince, National
Coordinator, Playtest Coordinator, Ethics Committee member — for twice the
duration of the suspension**, unless the Committee unanimously determines
otherwise.

There are **no other VEKN-recognized probations, suspensions or bans**. Organizers
and judges must allow all registered players in good standing to participate;
failing to may itself cost the organizer their Prince status, invalidate the
tournament's results, and draw sanctions. A list of probationary, suspended and
banned players is published on the VEKN forums.

Event-level penalties — Caution, Warning, Standings Adjustment, Disqualification —
are the Judge's Guide's, not the Ethics Committee's: [judging](judging.md).

## Ratings

Source: `reference/tournament-rules.md` Appendix A.

VEKN produces stats-based ratings for tournament results grouped as **Standard
Constructed (on site)**, **Standard Constructed Online**, **Limited (on site, all
formats in one group)** and **Limited Online**. Per-player performance statistics
(games, GW, VP) are maintained alongside.

**A.1** — each player has a single rating number, sometimes called **RtP**.
Players are ranked from their first tournament; there is no minimum number of
events. **A player is removed from the rankings after 12 months of inactivity**,
but their rating and statistics are kept indefinitely for when they play again.

**A.2** — the rating is a points accumulation over sanctioned tournaments in the
preceding **18 months**, counting **no more than 8** — for players with more, the
8 best results:

- **5 RtP** for each tournament attended
- **4 RtP** per victory point scored
- **8 RtP** per game won, **including a final round victory**
- **X RtP** for finalists, per A.2.1

**A.2.1 finalist bonus** — a number based on finishing position, multiplied by a
coefficient reflecting the level of competition:

| Final standing | Points |
|---|---|
| Winner | 90 |
| Finalist | 30 |
| Non-finalist | 0 |

`Coef = log₁₅(NumPlayers²) − 1` — the coefficient is 1 for a 15-player tournament,
larger above, smaller below. **+0.25 for a national championship, +1.0 for a
continental championship. Grand Prix and Qualifiers get no coefficient bonus.**

**The player count includes disqualified players and players who left during the
event, as long as they played at least one round** (A.2).

Worked example from A.2.1: a 50-player qualifier gives
`log₁₅(2500) − 1 + 0.25 = 2.139`, so the winner's bonus is `2.139 × 90 = 193`
rating points, on top of normal points for the round win and each victory point.

Results from tournaments run with card set restrictions are **excluded** from
ratings (§6.1.1), as are results from invalidated events (§9.4) and results
reported with placeholder player numbers (§9.6).

### Never chase vekn.net's stored RtP

*(Measured, 2026-07; recorded here because it is a fact about the upstream system,
not about our code.)*

A player's `rtp` on vekn.net can be **higher than ours and still be wrong**. VEKN
stores `vp` (preliminary) and `vpf` (finals) per player and its rating adds them.
Legacy archon pushed `vp` already including the finals VP, so every finalist it
uploaded carries `4 × vpf` too many points upstream. Our push sends prelim `vp`
with `vpf` separate, and is correct.

An inflated upstream value is then frozen there and unfixable through the API,
because the results upload is write-once. Observed behaviour is that vekn.net
keeps the `rtp` we push rather than re-deriving it from its own roster — verified
on vekn event 13453, where it stored our N=20 figures against a 19-row roster of
its own — but not universally, so do not rely on it either way.

**A gap between our number and vekn.net's is therefore not evidence our maths is
wrong**, and "align with vekn.net" is not a valid reason to change the engine or
the backend rating code. Decide against A.2 above, then check whether upstream's
figure is explained by the double-count. Verified example: Hungarian Finals 2026
(vekn 12836) — ours at 191 is right, vekn.net's 197 counts prelim and finals VP
twice.

Divergences worth acting on are the ones where *our* input is wrong — for instance
a rank the app cannot represent, so the coefficient bonus is missed.

## External systems

**vekn.net** holds the member roster, the event calendar and the tournament
record. Its API is what the app pushes to and pulls from
([vekn integration](../vekn.md)). Constraints that come from their side, not ours:
the API has **no delete-event and no update-event endpoint**, so the surface is
create-event, upload-results, create-member, fetch-venue, fetch-event,
fetch-all-events, search-players, fetch-all-members. **Every upstream correction is
therefore a human action on vekn.net**, and a calendar entry, once created, cannot
be edited through the API — an in-app edit to an already-pushed event never reaches
vekn.net.

**The TWDA** — the Tournament Winning Deck Archive — is the public registry of
winning decklists, hosted at `GiottoVerducci/TWD` on GitHub and mirrored as JSON
at `static.krcg.org/data/twda.json`. Winning a sanctioned event puts your name and
deck there; it is a public record of wins, which is why the winner's name is
always in the header of a submission regardless of who designed the deck.

**krcg** is the community card-data library the app sources canonical card data
from, and whose providers back deckbuilder-URL import.

**Black Chantry** prints the promo cards the app's promo catalog and inventory
ledger track; "BCP" as a ledger stock source means the printer.
