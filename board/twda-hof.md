> Elaborated context for a line in `BOARD.md`. Deleted with the line.
> `#N` below is a **retired tracker number**, not a GitHub issue and not a live
> pointer — the surrounding prose carries the fact. A real GitHub issue is
> written `gh-N`.

# TWDA sync — rebuilding the historic Hall of Fame

Born from user report gh-7 (a player comparing our Hall of Fame against
`vekn.fr/hall_of_fame.htm`). The report reads as a display bug; it is not. Our
HoF is derived from the vekn.net event corpus, and that corpus holds roughly
half the archive the reference counts.

**Settled** records the owner decisions; **Plan** is the work. Everything before
**Settled** is the analysis they rest on.

## The reference is a TWDA entry count

`vekn.fr/hall_of_fame.htm` states its criterion as "win a minimum of five IRL
tournaments (not online), and those tournaments must have had their results
posted on the official V:EKN Player's Forum". In practice that is exactly a
per-player count of TWDA entries — verified 2026-08-10 by counting `player`
strings in `static.krcg.org/data/twda.json`:

| Player | TWDA entries | Reference page |
|---|---|---|
| Marcin Watras | 19 | 19 |
| Tomasz Izydorczyk | 12 | 12 |
| Tomasz Pietkiewicz | 9 | 9 |
| Marcin Ruminski | 1 | absent |

The counts match line for line. So reproducing the reference needs no rule
reverse-engineering: sync the archive and count.

Ruminski is the tell in the other direction — 1 entry upstream, 5+ with us.
That difference is ours, not the corpus's (see *Two independent errors*).

## The corpus, re-measured 2026-08-14

Fresh pull of `static.krcg.org/data/twda.json` (4538 entries, 1997-04-11 →
2026-06-13):

| | count |
|---|---|
| entries total | 4538 |
| with an extractable VEKN event id (what we match today) | 2211 |
| **unlinked — candidates for reconstruction** | **2327** |
| — dated pre-2014 | 2257 |
| — dated 2014+ | 70 |
| `place == "Online"` (excluded from the HoF) | 126 |
| distinct winner name strings (normalised) | 1552 |
| **IRL names with >= 5 entries — the true HoF size** | **234** |
| of those, reachable with what we hold today | 115 |
| members sitting at exactly 5 (one win from the line) | 47 |

**Half the Hall of Fame is invisible to us**: only 115 of the 234 reach five
wins on linked entries alone. The 234's 2526 entries are 50% unlinked.

### The gap is a clean date cut, not a scatter

The TWDA only began carrying `vekn.net/event/` links around 2013:

| era | unlinked / total |
|---|---|
| 1997–2013 | 2245 / 2276 |
| 2014–2017 | 67 / 527 |
| 2018+ | 3 / 1735 |

This corrects the framing in gh-7 and in the original ticket text: it is **not**
a pre-2005 problem. It is pre-2014, and it is a *linking* gap, not necessarily
an *event* gap — see Phase 0, which is the single biggest hazard here.

`extract_vekn_event_id` returns `None` for anything whose `id` is not numeric
and whose `event_link` lacks `/event/`; the caller `continue`s, so more than
half the archive never enters the lookup. Of the unlinked entries 2175 carry no
`event_link` at all, and the rest point at `groups.google.com` (104),
`calendar.yahoo.com` (9), `vekn.fr` (7), `web.archive.org` (5) and others.

Notably 3 entries link to `archon.vekn.net/tournament/<uuid>/display.html` —
a *legacy-archon* URL scheme (we pass `""` as `tournament_url` to `export_twda`,
`routes/tournaments.py:357`, so these were not emitted by us). krcg derives the
entry `id` from the link, so emitting a tournament URL would make the round-trip
match deterministic for everything we submit from now on.

**That scheme is dead**: `archon.vekn.net/tournament/<uid>/display.html` 404s
today (verified 2026-08-14); the live route is `/tournaments/<uid>` (plural, no
`display.html`). So the matcher's first tier must parse **both** forms, and what
we emit going forward is `https://archon.vekn.net/tournaments/{uid}`.

## What a TWDA entry carries

```
id, event, event_link, place, date, tournament_format, players_count,
player, score, name, comments, crypt{...}, library{...}
```

Field completeness across the 2327 entries to reconstruct: `crypt`/`library`
2327 (**every one carries a decklist**), `players_count` 2234,
`tournament_format` 1472, deck `name` 1815. `place` is `"City (STATE), Country"`
— only **45 distinct country strings** across the whole archive, and the messy
ones are tiny (`England`/`Scotland`/`Wales` → GB, `United States`/`USA`,
`Russia`/`Russian Federation`, one malformed `Columbus OH USA`). 39 of the 45
resolve straight from the bundled GeoNames data, so `geonames.normalize_country`
handles them with five real aliases plus `USA`; from there `geonames.match_city`
resolves city + country, and its `_PAREN_RE` already strips the `(OH)` form.

Missing: any player identity beyond a display name, and any non-winner.

## Two independent errors, only one is the corpus

**Undercount** — structural, fixed by this ticket: we hold only events with a
vekn.net event id, so pre-2014 wins are invisible and veterans read low.

**Overcount** — ours, and it survives any corpus change unless addressed:

- `get_tournament_wins_for_users` (`backend/src/db.py:1288`) counts every
  finished non-online, non-house-format tournament with the user as `winner`.
  No player-count gate, no has-a-final gate — unlike ratings, which use the
  engine's `ranking_eligibility` (`backend/src/ratings.py:253`), and unlike our
  own TWDA auto-submission gate of 10+ players.
- `user.wins` is only ever written inside the loop at `ratings.py:315`, whose
  member set comes from pass 1 at `ratings.py:340-355` — and that pass *does*
  filter on `ranking_eligibility`. So the counting rule and the enumeration rule
  disagree: a player whose 5 wins are all in 6-player events gets no `wins`
  array and never appears, while the same player plus one appearance in any 8+
  player event gets all 5 counted and lands in the Hall of Fame. Membership
  turns on an unrelated coincidence.
- Duplicate imported events (one real event entered twice upstream under two
  vekn ids, `#521`) double-count a win. The prod dedup run is still pending and
  is deliberately sequenced post-flip in `#41`.

The rule below dissolves the split gate: one predicate governs both enumeration
and counting.

---

## Settled (owner, 2026-08-14)

1. **Reconstructed historic events are real `Tournament` rows**, not a new
   object type.
2. **The decklists are imported.** Note the ceiling in *The rule*: a
   `DeckObject` requires a `user_uid`, so only entries whose winner resolved can
   carry one. Deck coverage tracks identity resolution; it is not independent.
3. **Winner identity**: best-effort auto-attach to a *unique* member match,
   never silent member creation. A preliminary pass produces a review table the
   owner confirms, possibly approving a handful of member creations for winners
   who genuinely cannot be found.
4. **The HoF rule is "won AND submitted the deck."** Owner: *"It's not so much
   about the TWDA repo itself than it is about having won AND submitted the
   deck. It's encouragement to provide data. The TWDA is just currently our best
   list of winners and events, even better than the old vekn api, so we use it."*
   The TWDA is the **source of historic events and winners**, not the authority
   for counting — a native win with a stored decklist counts immediately, with no
   upstream round-trip. We keep pushing to the TWDA after decommission.
5. **Three floors, deliberately different** (owner, 2026-08-14): **8 players**
   to make the rankings, **10 players** to make the TWDA, and the **HoF counts
   follow the TWDA floor — 10**. A product review argued for reusing the 8-player
   `ranking_eligibility` floor on rule-text grounds (VEKN 3.1.6); the owner
   overrode it, and the override is the coherent call: the HoF is defined by deck
   submission, so it inherits the submission threshold, not the rating one.
6. **The HoF stays member-projected.** Owner: *"It's better than the vekn public
   version (member names should not bleed into non-member space)."* `wins` stays
   in `_USER_MEMBER_FIELDS` (`access_levels.py:83`); logged-out visitors get the
   explicit sign-in state already scoped in `#613` item 5, not an empty table.
7. **The VEKN record outranks the archive** (owner, 2026-08-16): *"The VEKN record
   is higher on the trust scale. TWDA is only when record does not have the
   info."* Where both describe one event the VEKN result stands and the archive
   fills only the gaps. Its sharpest consequence is that `reported_player_count`
   is stamped on archival rows and **never on a VEKN import** — see *Archival
   results*, which is what makes wiring the rating coefficient safe.

## The rule

A tournament counts as one Hall-of-Fame win when **all** hold:

- `state == Finished`, `deleted_at IS NULL`
- `online` is false (VEKN HoF convention, `#424`)
- not `open_rounds` / `self_organized_rounds` (house format)
- `format != Limited` (Limited decks are not archived; mirrors
  `maybe_submit_twda`)
- **>= 10 players who played** — the TWDA floor (`TWDA_MIN_PLAYERS`,
  `routes/tournaments.py:366`), not the 8-player rating floor
- has a final (or a `winner`, which the engine already treats as implying one,
  `engine/src/ratings.rs:63`)
- `winner` is set
- **a `DeckObject` exists for that winner on that tournament**

Five such wins = Hall of Fame. In one sentence: **a win counts when it would
have qualified for the TWDA and the winning deck is on record.** That is the
reference criterion restated in terms that survive the vekn.net decommission,
which is what keeps it non-arbitrary — and it makes the rule read the same for
both corpora, differing only in the evidence each supplies (for a TWDA entry,
presence in the archive *is* the submission and `players_count` satisfies the
floor; for a native event, a `DeckObject` and seated players do).

**The floor costs zero historic members** — measured twice, independently. Only
17 IRL entries in the whole archive are under 10 players, and applying the
10-floor yields the *same 234* members, **provided a missing `players_count`
grandfathers as eligible**. That proviso is load-bearing: excluding the 100
entries with a blank count instead drops 5 real members for a data gap.

Also settled:

- **Derived, never stamped.** VEKN rule 8.6 reserves the right to invalidate
  reported results, so there must be no persisted `hall_of_fame` badge that
  outlives a corrected result. The derive-from-`wins` shape is right.
- **Deliberately NOT added**: a "winner must hold a VEKN id" gate (rule 8.4
  would support it). An unresolved-name winner should be *pending*, not
  disqualified.
- **State the criterion on the page.** Once `vekn.fr` stops being maintained,
  our stated criterion *becomes* the definition. One line under the title. Never
  render a "vs vekn.fr" delta — that is an implementation artifact; the win list
  on `/users/[uid]` is what makes the number auditable.

Nothing in the VEKN rules defines a Hall of Fame at all — it is a community
artifact, so the criterion is genuinely the owner's to set (and he holds
Rulemonger + IC).

---

# Plan

Filed as children of this epic:

| ticket | phase | note |
|---|---|---|
| `#614` | Archival results | **foundation** — blocks `#617`, `#618` |
| `#615` | 0 — event reconciliation | read-only, gates every creation |
| `#616` | 1 — winner identity | read-only, feeds the same decisions file |
| `#617` | 2 — the sync | reconstruction + deck import + backfill |
| `#618` | 3 — the HoF rule | blocked on `#614` |
| `#619` | 4 — surfaces | p3 |
| `#620` | 5 — TWDA push survives decommission | independent, anytime |

Split out as **not** a child, because it is live on prod today across thousands
of VEKN-imported and ETL-migrated rows and should not wait on this epic:
`#621` (rounds-less display divergence + raw-UUID winner).

Sequencing: `#615` and `#616` run first and create nothing; `#614` can run in
parallel; then `#617` → `#618` → `#619`.

## Phase 0 — Event reconciliation — **done 2026-08-16, queue decided**

`backend/scripts/reconcile_twda.py` is landed and read-only; the generated proposal
table is `board/twda-event-reconciliation.md`. The queue is **decided** — the twelve
rows it lists have the rulings recorded below, and Phase 2 applies them to the
emitted TSV before consuming it. The script writes review rows into the TSV as
`review` lines rather than omitting them, so a consumer fed an undecided file sees
them and refuses instead of reading a short file as a complete one.

Against the live corpus:

| outcome | entries |
|---|---|
| attach — vekn id | 2177 |
| attach — winner + date (name-free) | 1177 |
| attach — winner + date + player count | 28 |
| attach — winner + date + event name | 11 |
| attach — our own link | 3 |
| **create — no candidate** | **1130** |
| **review — needed a human** | **12** |

**The reconstruction is 1130 events, not the 2257 this plan sized it at.** The
"mostly linking, not importing" claim below is confirmed and then some, and the
review queue was twelve decisions rather than hundreds. The name-free tier measures
**99.9% precise at 95.8% recall** against the linked entries as ground truth, and
both of its two remaining misses are artifacts rather than defects: one is scored
against the `delete me` row (the tier is right and the ground truth is wrong), the
other follows a TWDA date a month off its true one, which the vekn id fixes on the
real run.

Six design corrections the measurement forced, all already in the script:

- **Comparing names needs a real ASCII fold, not an NFD mark-drop.** ł does not
  decompose, so `Paweł` normalised to `pawe` and never met the archive's `Pawel`.
  Six Polish events were reconstructing as duplicates, `Polish NC 2009` and
  `Polish ECQ 2011` among them — the cohort three of whose players are this
  epic's done-condition. The fold now goes through `geonames.fold_ascii`, which
  gained the engine's explicit map; recall rose 95.6% → 95.8% at unchanged
  precision.

- **The vekn event id is not proof of identity.** Entry `12797` names an id its
  submitter abandoned; ours holds a 0-player row called `delete me` while the real
  event is `12794`. But a disagreeing winner name alone must **not** unseat the id —
  75 entries disagree harmlessly because our names are fuller than the archive's
  (`Javier Naranjo Ortiz` vs `Javier Naranjo`). Only a rival event on the same date
  won by the same player does. An id we do not hold falls through to the name-free
  tier instead of going straight to review.
- **In a TWDA entry `name` is the DECK name; the event name is `event`.** Keying
  the tie-break confirmer on `name` compares decks to tournaments and silently
  never fires.
- **The two `event_link` url forms quote uids from two different id spaces.** The
  live `/tournaments/<uid>` form quotes ours; the dead legacy
  `/tournament/<uid>/display.html` form quotes the uid *legacy archon* minted, which
  the import kept in `external_ids['archon']` on 255 rows. Looking only in our own
  uid space reported both legacy links as dead — and the Valencia one would then
  have been reconstructed as a duplicate, since the archive abbreviates its winner
  (`Jose Vte Coll` against our `Jose Vicente Coll`) and no weaker tier can reach it.
- **The player count is the confirmer that breaks the same-weekend clusters.** TWDA
  `players_count` and our seat count agree *exactly* on most of the multi-event
  weekends the name-free tier stalls on — a convention running four tournaments one
  player each won. Added as a tie-break behind the event name it resolved 28 of the
  39 rows the queue opened with, at zero cost to precision on the labelled set.
- **A per-entry matcher cannot see that two entries claimed one tournament.** The
  TWDA holds one winning deck per event, so a collision means at most one claimant
  is right and the loser is an event we do not hold. A pass over the whole verdict
  set now demotes the weaker tier's claim back to the queue, and a tie demotes both.
  It caught two: `Blood League part IV.` had landed on `Breath of the Dragon`, and
  `SuperHappyFunSlide Day 2` on `Day One`. Both losers are genuine reconstructions —
  without the pass, one win would have been mislabelled and the other lost entirely.
- **The non-discriminating-name denylist below was not built, and is not needed.**
  It guards a name-keyed matcher; the shipped one never keys on a name, so a
  repeated or generic event name cannot produce a false match in the first place.
  What survives from that paragraph is the *display* obligation — a row named
  `tournament` is unusable in the UI, so Phase 2 still synthesizes a name from
  `place` + date at review time.

### The decided queue

Ten attach, two create, no skips. Six of the attaches are forced by elimination:
their partner entry from the same weekend was resolved by an exact player-count
match, leaving exactly one candidate free. `2k5originssat` is the weakest of the
twelve — the counts fit the *other* candidate, and only the date carries it.

| twda id | ruling | grounds |
|---|---|---|
| `11429` | **create** | `Blood League part IV.` is not ours — we hold parts 1, II and III only. It had landed on `Breath of the Dragon`, which that event's own vekn id claims. |
| `12797` | attach `019f1a1a-ba64-74fd-bc9f-0fed297e0263` | The abandoned id points at a 0-player shell named `delete me`; the real event carries 11 players, 2 rounds and its own legacy archon id. |
| `2010ecday1` | attach `019f1a07-70ec-733f-a444-8a767501cc72` | Exact date and name. The archive's 155 is the whole Day 1 field; our row holds the 3rd group, 39 seats. |
| `2010originsthu2` | attach `019f1a07-7ab5-7344-9f59-b10bca00efaf` | `PM` matches 5pm, and the 11am entry took `Origins Thurs AM` on an exact 24 = 24. |
| `2010pwblaQ` | attach `019f1a07-7811-70f5-8ecf-ae1ce130e8e0` | Exact date, `Event #2` on both sides. We hold only events #2 and #3 of that Strategicon, both won by Keeney, so the archive's own numbering runs one behind ours. |
| `2010shfsd1` | attach `019f1a07-789f-74cf-af36-be4ff5263c3b` | Exact date, `Day 1` is `Day One`. |
| `2010shfsd2` | **create** | We hold Day One only; the ± 1 day window had pulled Day 2 onto it. |
| `2013jbflac` | attach `019f1a18-aabd-7114-aa47-285296579918` | Exact date; our name is the archive's plus a ` - Gamex 2013 - Event #2` suffix. The Haymaker entry took the other on an exact 10 = 10. |
| `2k5originssat` | attach `019f1a05-f050-71bf-86c8-78680ad7c182` | 2005-07-02 was the Saturday the entry names, and that row is the only one on it. Neither candidate's count matches, so size casts no vote. |
| `2k5originsthur4` | attach `019f1a07-2d4d-732a-9d55-9c3d0c6471ad` | The 10am entry took the 10:00 / 24p row on an exact match; 12 ≈ 13, and the 04:00 start is a 4pm event with a 12-hour slip. |
| `2k7losangelesqual` | attach `019f1a06-cfaa-75f5-b814-9969c052f6f9` | Exact date, both name the qualifier, 12 ≈ 13. |
| `2k9italychamp` | attach `019f1a05-cd31-71a5-93f0-bcfe0aebe883` | Exact date; `Campionato Italiano 2009` is `Italian NC 2009`; 27 ≈ 26. |

Re-running the script after the archive grows reopens the queue with these same
twelve plus whatever is new. The rulings above are keyed on the stable TWDA entry
id, so they can be reapplied rather than re-derived.

The rest of this section is the standing rationale for that design.

**This phase gates every later one. It creates nothing.**

**Duplicate risk is the biggest hazard in this ticket, and it is measured, not
theoretical.** The 2257 pre-2014 unlinked entries are *unlinked*, which is not
the same as *absent*. Counted 2026-08-14 from the live anonymous
`GET https://archon.vekn.net/snapshot` (public projection, 8466 live
tournaments, 8352 Finished):

| era | our tournaments | TWDA entries needing reconstruction |
|---|---|---|
| 2004–2013 | **3627** | 2257 |
| 2014+ | 4838 | 70 |

Our corpus reaches back to **2004** with heavy coverage of exactly the period the
TWDA fails to link (2004: 355, 2005: 533, 2006: 459, 2007: 529, 2008: 472,
2009: 425, 2010: 322, 2011: 78, 2012: 163, 2013: 291). So the overwhelming
majority of those 2257 entries are near-certainly events **we already hold** —
we simply cannot see the link. Reconstructing blind would mint on the order of a
thousand duplicate tournaments: `#521`/`#567` at ten times the scale, and unlike
those, self-inflicted.

This also reframes the ticket's *value*: the win is mostly **linking**, not
importing. Most of the missing Hall of Fame is already in our database as
unattributed events.

(Aside, unrelated to this ticket: that count also surfaced one tournament dated
**2034** — a data-entry typo, since recorded in `wiki/vekn-decommission.md`.)

Resolve every TWDA entry against the live corpus, in order:

1. `event_link` → a tournament uid — parse **both** the live `/tournaments/<uid>`
   form and the dead legacy `/tournament/<uid>/display.html` form, and look each up
   in **both** id spaces: our uid, then `external_ids['archon']` for the uid legacy
   archon minted. **Validate it resolves to a live tournament**; a stale or mistyped
   link must route to review, never fall through to name matching.
2. numeric `id` / `vekn.net/event/<id>` → `external_ids['vekn']` (today's path)
3. fallback: **a name-free match on date ± 1 day, winner name and country**, with
   the event name and then the player count breaking a tie.
   `find_same_event_tournaments` is *not* it — that query keys on the event name,
   which is the one field this corpus cannot use. It keeps the ± 86400s window and
   the country filter this tier also wants, which is why it read as the obvious
   precedent; the shipped matcher borrows those two rules and drops the name.

Then a pass over the whole verdict set, which is the only place a collision between
two entries claiming one tournament is visible at all.

**Do not use `DUPLICATE_GROUPS_QUERY`'s day-bucket key** (`db.py:1233`) even
though it looked like the obvious precedent. It buckets on
`(start AT TIME ZONE 'UTC')::date`, while TWDA `date` is a bare *local* date and
our `start` carries a *guessed* venue timezone (`vekn_tournament_sync.py:166`) —
any event in Australia, Japan or US Pacific routinely lands on the adjacent UTC
day. `#567` already documents this exact blind spot (PennyBridge - Charisma III,
"its two copies sit a day apart"). `SAME_EVENT_QUERY` uses a ±86400s window plus
an optional country filter, and is the key `_adopt_same_event` already matches
on, so the two agree by construction.

### Event names are a weak key — measured, and this drives the matcher design

Also from the 2026-08-14 prod snapshot, matching the 2257 unlinked pre-2014 TWDA
entries against the names of our 3627 pre-2014 tournaments:

| | count |
|---|---|
| TWDA event name matches **exactly one** of our tournaments | 500 |
| matches **several** (ambiguous) | 191 |
| **matches no tournament name of ours at all** | **1566** |
| shares a **date** with >= 1 of our events | 1647 |

So name matching resolves at best 22%, while 73% share a date with something we
hold. TWDA names and our names (mostly legacy-archon ETL) simply disagree —
different transliterations, abbreviations and outright placeholders.

**The placeholder cohort is the reason.** 869 of our 3627 pre-2014 tournaments
are literally named `"Imported VTES Event"` — 24% of the era, and the exact class
`_adopt_same_event`'s docstring warns about (`vekn_tournament_sync.py:378-382`).
For those, the event name carries *zero* information and no name-based key can
ever work.

Consequence for the design: **the matcher must have a name-free path.** Match on
`(date ± 1 day, country, winner name)` with the event name ignored entirely, and
treat the event name as a *confirmer* when it happens to agree rather than as the
key. This inverts the straw man above — winner name is not a tiebreak, it is the
primary signal for most of the corpus.

**Pleasant side effect worth stating as a deliverable**: the TWDA holds real
event names for events we hold as `"Imported VTES Event"`. This ticket can
**restore genuine names to hundreds of nameless legacy events** — arguably a
bigger visible win than the Hall of Fame itself.

**Answered on prod 2026-08-16 — the winner-name matcher is strong.** Of the 3627
pre-2014 live tournaments, **3516 (96.9%) carry a `winner`**, and every one of
those resolves to a live user with a name — no dangling uids. `country` is set on
3278 (90.4%), so the second confirmer is real. The `Imported VTES Event` count
reproduced exactly at 869.

**And every one of the 3627 has zero rounds** — the archival shape is not
something the reconstruction introduces, it is the existing shape of the whole
historic corpus. It costs Phase 3 nothing, though: all 3627 also carry scored
standings, which is the branch `players_with_rounds` falls back to. See *Archival
results*.

Confirmers, strongest first:

1. **Winner-name confirmation — the primary confirmer, not a fallback.**
   Resolve the candidate's `winner` uid to a `User` and compare the normalised
   name against the TWDA `player` string. A hit is near-certain identity even
   for a generic event name, and it is fully independent of name+date.
2. `country` from TWDA `place` (already supported by the query's filter).
3. `players_count` as a **tiebreak only, never a rejecter** — our imported
   player lists silently drop players whose VEKN id we don't hold
   (`vekn_tournament_sync.py:222-224`), so `len(existing.players) <=
   twda.players_count` is the *normal* case, and a hard equality gate would
   reject good matches at scale.

**Non-discriminating names**: don't special-case the literal string
`"tournament"` (50 entries). Derive the denylist from data — any normalised TWDA
name occurring more than once in the corpus, or matching more than one of our
rows on name alone within the same year, goes to review with no auto-match and
no auto-create. Same reasoning `_adopt_same_event` already encodes
(`vekn_tournament_sync.py:378-382`, on legacy placeholder names). A row named
`tournament` is also unusable in the UI and un-dedupable forever: synthesize a
display name at review time from `place` + date (`"Tournament — Kraków,
2007-03-17"`) and make the reviewer confirm it.

**Output**: a decisions TSV, following the established
`--emit-decisions` / `--apply` pattern (`backend/scripts/dedup_tournaments.py:16-18,
219-295`) — `twda_id <TAB> action <TAB> target`, action ∈
`create` / `attach:<tournament_uid>` / `winner:<user_uid>` / `skip`. That file is
the durable, reviewable, committable artifact **and** the answer to the
"re-runnable review queue" question: do **not** build an in-app object type for
this (it would cost a `BaseObject`, three projections, an SSE level decision and
an IndexedDB store for a one-time-plus-trickle operator workflow). The recurring
sync reads the file (packaged via `importlib.resources`, per CLAUDE.md) and is
then fully idempotent and deterministic: unreviewed entries are logged and
skipped, never created. Also write the human-readable table to
`board/twda-event-reconciliation.md` the way the duplicate table was.

Committing the mapping is fine under the no-PII rule: TWDA already publishes
every winner name alongside its event, and our uids are meaningless outside the
app.

## Phase 1 — Winner identity — **done 2026-08-17, 95.1% resolved at 100% precision**

**Re-derived 2026-08-17, when the matcher moved into `reconcile_twda.py`.** The
96.7% first reported here came from passes that only ever ran in a scratchpad, and
re-running them under measurement found one wrong match in 1121: the
surname-anchored classes were auto-applying on surnames dozens of members share,
where the given name carries the whole claim. Gated at
`MAX_SHARING_SURNAME`, the passes score **100% precise over 1116 labelled names**.
The gate held back 9 names / 11 entries, all plausible on sight; the owner
confirmed all nine on 2026-08-17 and they are rulings now, which is why the
coverage lands back at **1076 of 1132** with none of it resting on an
unmeasured class.

The number to hold on to is not the coverage: **zero of the 41 unresolved names is
HoF-relevant** (none has 5+ IRL entries), so no Hall of Fame place turns on the
queue — the same conclusion the first pass reached. What it costs is archival
completeness on 56 entries and the decklists that come with a resolved winner.

Both halves are now re-derivable — `--validate` scores the winner passes against
the bootstrap the same way it scores the event tiers, and every human decision
lives in `backend/src/data/twda_rulings.tsv` instead of a chat log.

The archive gives a name string and nothing else: 1549 distinct normalised
winner names, 234 of them at >= 5 IRL entries.

**Phase 0 shrank this phase by an order of magnitude.** The bootstrap reads the
name → member mapping straight off our own data — every attached entry hands over
the resolved `winner` uid of the tournament it attached to, with no name matching
at all. Against the decided queue that is **1156 of the 1549 names**, leaving
**393 needing true matching, of which only 8 are HoF-relevant**: Rob Treasure
(18 IRL entries), Josh Duffin (10), David Quinonero Santiago, Sten During and
John Newquist (7 each), Tomasz Kowalewski (6), Michael Courtois and Alex Ek (5).
The plan sized this at 740 names and 61 HoF-relevant off the 2211 linked entries;
the reconciliation's 3406 attaches absorbed the rest — Torstensson, Bell, Tatu
and Messer, named here as the hard cases, are all bootstrapped now.

**And the mapping is only ever consulted for the reconstruction.** An attached
entry's winner is the tournament's `winner` uid by construction; only the 1132
`create` entries need a name resolved. 634 distinct winners among them, 241
already bootstrapped, so **544 reconstruction entries across 393 names** are the
actual work — and an unresolved one costs one archival row, not a HoF place,
unless its name is one of the 8.

1. Bootstrap from the attached entries. One name mapping to two different uids is
   a genuine homonym — flag it, never merge. **Measured: 3 of 1156**, each a lone
   entry against a 3-to-31-entry majority, and only one of the three
   (`Gines Quinonero`) is reached by any reconstruction entry at all. Two of the
   three are not homonyms but *disagreements* — see below.
2. For the remaining 393, match the normalised name against `User.name`
   (`vekn_sync.py:558` builds it as `"firstname lastname"`, the same shape as
   the TWDA string), folding through `geonames.fold_ascii`. Require a **unique**
   hit. Measured against the 18982-member roster: **227 auto, 164 unknown, 2
   ambiguous**.
3. **Country is not even a tie-breaker.** The plan had it as one, on the grounds
   that top players travel — 107 of the 237 >= 5-entry names appear in more than
   one country. The measurement is worse than that: used only to break a tie
   between two same-named members it fired **4 times and got 1 wrong**, against
   1095/1095 for the unique-name path. It is dropped, and those cases go to
   review. The miss is instructive — `Julien Guérand` of Paris and
   `Julien Guerand` of Los Angeles are two real members, and the French one's
   entries include US events. `"Online"` is a pseudo-country in `place` and must
   not be read as one either.
4. **Validated against the bootstrap, which the matcher never saw**:
   **1095/1095 = 100% precision at 95.0% recall** over the 1153 unambiguously
   bootstrapped names. Auto-attach on a unique name hit is safe.
5. Emit `auto` / `ambiguous (N candidates)` / `unknown`, sorted by entry count
   descending so HoF-relevant names are reviewed first. Owner confirms; a
   handful of member creations may be approved for the genuinely unfindable.

### The near-match pass — surname-anchored, scored per class

The six HoF-relevant names the exact matcher missed were resolved by hand, by
searching the roster for the surname and reading the candidates. That method
generalises, and the generalisation is what recovered most of the tail — but only
once each class is scored **separately** on the bootstrap's own 58 misses, where
the truth is known and the class never saw it:

| class | what it matches | bootstrap | verdict |
|---|---|---|---|
| `member-subset` | the archive carries surnames the member record drops — `David Quinonero Santiago` → `David Quiñonero` | 7/7 | **auto** |
| `given-prefix`, <= 3 share the surname | one given name is a prefix of the other — `Josh` → `Joshua` | 9/9 | **auto** |
| `diminutive` | a curated nickname table — `Tomek`/`Tomasz`, `Mike`/`Michael` | 1/1 | **auto** |
| `given-prefix`, >= 4 share the surname | same, on a crowded surname | 7/8 | review |
| `given-fuzzy` | given names merely similar | never fired | review |
| `surname-only` | nothing but the surname agrees | 0/1 | **rejected** |

`surname-only` is not a weak signal, it is the wrong one: its proposals are
`Caroline Hyll` → `Kari Hyll`, `Jennifer Goldberg` → `Paul Goldberg`,
`Peter Korsos` → `Attila Korsos` — relatives and strangers, not spellings. It is
refused outright rather than sent to review, because a reviewer reading 44 of
those learns to click through them.

Two guards the measurement forced, both of which had produced real false
matches:

- **A one-token member name cannot satisfy `member-subset`.** A member recorded
  as `Nick ?` is a subset of every `Nick <surname>` in the archive.
- **The length floor on a prefix applies to the shorter side.** Anchored on the
  longer one, an initial or a particle matches: `James Rodriguez` took
  `Miguel **J.** Blázquez Rodríguez`, and `Daniel Mota` took
  `Hudson Silva **da** Mota`.

The rejected token-subset fallback from the first pass — archive tokens a subset
of the member's — is what `member-subset` became once inverted and guarded. In
its original direction it scored 93.3% and put a Brazilian's win on a different
real member; inverted, it is 7/7.

**57 names auto-accept** and 18 more were confirmed by the owner, taking
reconstruction coverage from 900 entries (79.5%) to **1020 (90.1%)**.

### The fuzzy pass — for surnames that are misspelled, not just abbreviated

Every class above anchors on an *exact* surname, so none of them can reach a
surname the archive typed wrong. A whole-name similarity pass over the roster
closes that: `Riku Niittymaki` → `Riku Niittymki` (the member record lost its
`ä`), `Scott Christoferson` → `Scott Christofersen`, `Kirill Samoilov` →
`Kirill Samoylov`. Both bootstrap names that reached it matched correctly, and it
independently recovered the two the prefix bug had sent to the wrong member —
`James Rodriguez` is `James Rodri**q**uez`, `Daniel Mota` is `Daniel Mo**tt**a`.

Three guards, each forced by a false match it produced:

- **A lone given name identifies nobody** — `Michele` matched `Michelle`.
- **The runner-up must be clearly worse**, or two members are equally close and
  the pass refuses rather than guessing.
- **The archive's surname must have a counterpart scoring >= 0.75 somewhere in
  the member's name**, or the member's name must be contained in the archive's.
  A whole-name ratio clears the floor on given name and length alone:
  `David Magri` reached `David Martín` at 0.87. Comparing *last* tokens is the
  obvious form of this guard and is wrong — Spanish double surnames put the
  counterpart in the middle (`Juan Luis Mejías **Luna**`), and it threw away both
  known-correct matches. `magri`/`martin` scores 0.727, which is why the floor is
  0.75 and not 0.7.

29 further names, coverage to **1050 entries (92.8%)**.

### The leading-prefix class — the archive kept only the first surnames

Building the review queue exposed a class hiding in it: `César Brera` sitting
next to `César Brera Márquez`, `Claudio Soulié` next to
`Claudio Soulié Caratte` in the very city the event was played. That is the
Iberian and Brazilian convention of a second surname the archive dropped, and it
is the *inverse* of `member-subset`.

Taken as a plain token subset it is the fallback rejected twice above at 93.3%.
Requiring the archive's tokens to be a **leading prefix** of the member's, rather
than merely contained in it, scores **4/4** and — decisively — kills the known
error: `Matheus Oliveira` cannot prefix `Matheus **Rocha de** Oliveira`, while
every true match only ever *appends*. 13 further names, coverage to **1068
entries (94.3%)**.

Country is again not used. Exactly one row would have needed it — `Tim Smith`,
where the gate produces a unique answer only by discarding a second `Tim Smith`
whose country is **unknown rather than different**, the failure
[hazards](../wiki/hazards.md) names. It is in the review queue instead.

### What no pass could resolve

**64 entries over 50 names.** The queue is a per-name table of the wins with
their dates, events and player counts, and every member who is plausibly that
person, **grouped by the country the wins were played in** so a section can be
handed to the official who would recognise the names. Candidates are scored, not
merely collected: a shared given name alone drags in every `Claudio` in the
roster, so playing in the same country as the wins is weighted as heavily as the
name signal.

**That table cannot live in this repo.** Its candidate columns are roster data —
member name against VEKN id and city — and the repo is public
([dogmas](../wiki/dogmas.md#dependencies-and-data)). The TWDA half of each row is
already public, the roster half is not. It is delivered out of band, and the
generator writes outside the tree. Only the *decisions* it produces come back
here, as `winner:<user_uid>` lines in the decisions file, where a uid means
nothing outside the app.

None of the 50 reaches five wins, so **no Hall of Fame place turns on that
queue** — what it buys is archival completeness and the decklists that come with
a resolved winner. Several rows will have no right answer: a 2005–2010 winner who
never registered with the VEKN is not in the roster, and *no member* is the
correct verdict. Those stay held out of the import rather than imported
winner-less, per the rule below.

#### Decided by hand, owner 2026-08-16

23 of the 50, leaving 37 entries over 27 names and taking coverage to **1095 of
1132 (96.7%)**. Every VEKN id given was checked to exist and to carry the name
claimed for it. Recorded as uids, which mean nothing outside the app; the
membership numbers stay out of this public repo.

| archive name | member | uid |
|---|---|---|
| Alejandro Hernandez Molina | Alejandro H. Molina | `019f1a00-ad0c-77a5-8a54-4fde20bbf720` |
| BJ Conant | Brian J. Conant | `019f19ff-8b14-72f7-aa69-4cc6ba29a53b` |
| Ben O'Neill | Ben ONeill | `019f1a00-78c6-775b-9abe-ee9d668bd22e` |
| Bernie MacNaught | Bernard MacNaught | `019f1a00-7ad6-76d4-b406-07930b3a7995` |
| Bruno Keiti Tamane | Bruno Keiti | `019f1a00-9750-750c-98a5-f6cac873c649` |
| Caroline Hyll | Kari Hyll | `019f19ff-b402-779c-932c-99168acfc5fa` |
| Daniel Stefanutti | Daniel Albert Stefanutti Lindemann | `019f1a00-99b0-74c4-82b6-02c60be77f1a` |
| Denny Bruset | Danny Buset | `019f1a00-6fa7-7124-a580-f8286a140696` |
| Eric Haas | Eric Haas | `019f1a00-cb3d-709f-97d7-0cc13d04f27f` |
| Jeff Lamothe | Jean-François Lamothe | `019f19ff-bb89-72fa-80f8-f715da313543` |
| Jessie Ellison | Jessica Ellison | `019f1a00-0ca1-7118-9a42-c5cb884647ad` |
| Karl Cheng Chua | Karl Ian Uy Cheng Chua | `019f19ff-8d41-7753-bec8-f9766c35afda` |
| Lander Ladislao | Lander | `019f19ff-c1b2-73a8-a55f-c77bb71a4b5a` |
| Mattrim Dixon | Matthew Dixon | `019f19ff-8a0d-7379-8a21-bb8d74ce59c5` |
| Michael Corriea | Micheal Correia | `019f1a00-590f-767f-9fb2-e12baf29eade` |
| Michael W. Jones | Michael Jones | `019f19ff-f6b5-7547-9d3b-1d9961c8d961` |
| Michele | Michele Polo | `019f19ff-9b2d-73bf-adc6-0f22875e1991` |
| Miguel Vazquez | Miguel Angel Vasquez | `019f1a00-9aaf-7311-ac03-7ac9fb108439` |
| Pau Villar | Pau Vilar | `019f19ff-958f-7525-9cbe-7c09d97b6fd0` |
| Peter Jaworski | Piotr Jaworski | `019f19ff-d108-7768-b0c7-7d86834194bc` |
| Robert Müller | Robert Mueller | `019f1a00-7178-7411-b905-17f89b980eaf` |
| Steve Van Nus | Steve Vannus | `019f1a00-7a78-7520-b2bf-de27662ae01a` |
| Tim Smith | Tim Smith | `019f1a00-7c54-7373-bedc-ecd71868c096` |

`Tim Smith` and `Eric Haas` are the two the automated passes refused on purpose —
each had a second member of the same name, and the owner picked between them.

`Caroline Hyll` → `Kari Hyll` was corrected on review: the first ruling reached a
`Caroline Vallee` in Québec against wins played in Stockholm, where `Kari Hyll`
shares both the surname and the city. It is the one row where the generated
candidate list ranked the right answer first and the hand pass took a lower one —
worth remembering as the failure mode of a long queue, not of the matcher.

### The six HoF-relevant names — confirmed by the owner 2026-08-16

None needed a member creation. Every one is a given-name variant or a dropped
second surname:

| archive name | IRL entries | the member | vekn id | where |
|---|---|---|---|---|
| Josh Duffin | 10 | `Joshua Duffin` | 1000085 | US, Washington DC |
| John Newquist | 7 | `Jon Newquist` | 2020029 | US, Atlanta |
| David Quinonero Santiago | 7 | `David Quiñonero` | 3190006 | ES |
| Tomasz Kowalewski | 6 | `Tomek Kowalewski` | 8500001 | PL, Bytom |
| Michael Courtois | 5 | `Mike Courtois` | 2200032 | US, Los Angeles |
| Alex Ek | 5 | `Alexander Ek` | 3380042 | SE, Göteborg |

Tomek is the Polish diminutive of Tomasz. `Courtois` has a second live member,
`David Courtois` of Paris, who is a different person. The Quiñonero surname is
the same family cluster as the Palma disagreement recorded in
`wiki/vekn-decommission.md`.

The other two of the eight resolved automatically: Rob Treasure (18 entries) and
**Sten Düring** (7) — the latter only because the ASCII fold now works, since the
archive spells him `Sten During`.

**Expect the roster to spell names differently from the archive.** Measured over
the 2180 entries the two name-blind tiers matched — pairings established without
ever looking at a name, so the disagreements are real drift and not matcher error
— 2107 agree exactly and **73 do not**: 34 where our name is the fuller one
(`Javier Naranjo` → `Javier Naranjo Ortiz`), 13 where the archive's is, 23 typos,
transliterations and nicknames baked into the member record
(`Mateus Silva De Souza` against our `Mateus "The Doctor" Souza`), and 3 outright
disjoint. So an exact-match-only matcher will miss around 3% of resolvable names,
and that is the floor to judge step 4's precision against.

**Two of our live rows disagree with the archive about who won**, surfaced free by
the bootstrap and recorded in `wiki/vekn-decommission.md` for IC curation: the
2023-10-22 Palma event `Matusalén,¿dónde está mi promo?` and the 2021-09-19
Brazilian `Roundhouse`. Both came to us through their vekn event id, so the
disagreement is between the vekn.net result and the deck the archive holds for it;
one side is wrong and neither is ours to decide.

**Entries whose winner never resolves are held OUT of the import**, in the
re-runnable queue — not imported winner-less. `Tournament.winner` is a user uid
and there is no winner-name field, so importing unresolved would mean a new
model field plus projections plus frontend fallback rendering. Worse, such a row
contributes nothing to the HoF (the rule needs a winner *and* a deck), renders
as an empty stub, cannot carry its deck at all (see Phase 2), and — having zero
players — becomes adoptable by `_adopt_same_event`, i.e. a live duplicate
magnet. What is lost is "the archive is complete" as a visible property;
mitigate with a counter in the report, not with orphan rows.

## Phase 2 — The sync — **done 2026-08-17**

All seven items landed, plus every trap below that guards them. What the build
settled that the plan did not say:

- **The winner identity had no durable home.** Phase 1's passes lived in scratchpad
  scripts and its rulings in chat, so this phase could not write `winner=<uid>` at
  all. Both moved into `reconcile_twda.py` and `backend/src/data/twda_rulings.tsv`
  first — see the Phase 1 note above, including the wrong match that surfaced.
- **Item 1 went further than "its own schedule".** `TWDA_SYNC_ENABLED` /
  `TWDA_SYNC_INTERVAL_HOURS`, registered outside the `VEKN_SYNC_ENABLED` block, so
  the archive sync survives `#579` deleting the chain. Set in both inventories.
- **Two silent degradations the traps implied but did not name**: a decisions file
  gone stale against the corpus attaches nothing, and a reconstructed row whose
  archive entry disappears is invisible. Both are counted in the sync stats and
  logged; neither is ever auto-repaired.

- **The scheduled task cannot become the backfill.** `MAX_CREATES_PER_RUN` caps a
  run at a delta; over it, it reconstructs nothing and names the script. Found by
  asking whether the deploy could precede the backfill — it can, and with
  `TWDA_SYNC_ENABLED` true in both inventories it would have run the bulk with
  broadcasting on, which is the one thing item 6 exists to prevent.

**Still owed before this reaches the corpus**: regenerate
`twda_decisions.tsv` against prod (it was generated from the 2026-08-16 extract,
and its targets are uids), then `backfill_twda.py --apply`. The recurring task
handles only the delta after that.

### The plan, as executed

1. **Make `twda_import.py` standalone.** It is currently chained inside
   `run_vekn_sync` (`main.py:187-196`) and dies with `#579`. Give it
   `run_twda_sync()` on its own schedule, and route the outcome through
   `record_success`/`record_error` (`vekn_status.py`) like the member and
   tournament syncs (`main.py:169-176`) — today it only logs, so a persistent
   failure is invisible on the status page. With the archive becoming the sole
   source of historic wins, that is not acceptable.
2. **Delete the ETag short-circuit** (`twda_import.py:17, 116-118, 123-127`).
   It returns before any reconciliation on a 304. Harmless today; once identities
   are attached from the decisions file, *our* side changes while the archive is
   stable — a member is created, renamed, or claims a VEKN id — and the sync
   304s forever without re-attaching. Silent and permanent. A 12 MB fetch every
   6h against a static CDN is not worth that. If kept, it must gate only the
   network fetch, with the reconcile pass running unconditionally against a
   cached parse.
3. **Reconstruct** unmatched entries as `Tournament` rows in the canonical
   rounds-less legacy shape, which already exists in prod
   (`vekn_tournament_sync.py:215-321`, `migrate_from_archon.py:1066-1163`):

   ```
   state=Finished, rounds=[], finals=None,
   players=[Player(user_uid=<winner>, state=Finished)],
   standings=[Standing(user_uid=<winner>, finalist=True, gw/vp/tp=0)],
   winner=<uid>, external_ids={"twda": <entry id>},
   league_uid=None
   ```

   The single `Player` row is **not optional** — see *Traps*. **Scores stay
   zero**: TWDA's `score` is the winner's *total including the final*, while
   `standings` is contractually prelim-only, so deriving a split from that
   unstructured string would plant a guess where later math will trust it. The
   row carries no league, and it is rating-ineligible **because of the
   `"no_results"` guard** added in *Archival results* — not automatically. Zeros
   are harmless only while that guard stands.
   Also set `reported_player_count` from the entry's `players_count`.

   `_parse_rounds` (`vekn_tournament_sync.py:81`) reads `"3R+F"` → `max_rounds`;
   `_parse_date` (`:94`) reads the ISO date into the naive wall-clock the model
   wants; `_guess_timezone` plus the 45-entry country alias map and `match_city`
   fill timezone/country/city.
4. **Persist `players_count`** — required by the rule, see *Traps*.
5. **Import the decks** for reconstructed *and* already-matched events, reusing
   the existing `DeckObject` shape with `attribution="twda"` (the TWDA export
   path already understands that sentinel, `routes/tournaments.py:330`).
   **Ceiling**: `DeckObject.user_uid` is required (`models.py:518`) and
   load-bearing in three places — `idx_objects_deck_user` (`schema.sql:225`), the
   SSE personal overlay, and the frontend `by-user` index (`db.ts:242`). A deck
   with an empty `user_uid` is a member-visible orphan owned by nobody that
   pollutes the by-user index for every viewer. So **only entries with a resolved
   winner can carry a deck**, and review throughput gates deck coverage. The
   measured corpus size — 4.1 MB raw JSONL / **1.0 MB gzipped**, avg 36 distinct
   cards per deck, member-level only (`compute_deck_public` returns `None`) — is
   an upper bound, not the delivery. Re-measure after Phase 1.
6. **Run the bulk backfill as a one-time script, not as the task's first run.**
   Creating ~2300 tournaments + decks through `save_object_from_model` +
   `broadcast_precomputed` in a tight loop would push thousands of SSE frames to
   every connected client in a burst. (The VEKN sync has the same shape but is
   spread across a slow HTTP-bound loop, so it never showed.) Suppress
   broadcasting, then regenerate the snapshot (`snapshots.py:49`), as the
   migration did. The recurring task then only handles the weekly delta, where
   per-object broadcast is correct.
7. **Add `idx_objects_tournament_twda`** to `schema.sql`, mirroring `:212-214`.
   Without it every `get_tournament_by_external_id('twda', …)` (`db.py:1140`)
   seq-scans ~30k tournament rows, ~2327 times.

## Phase 3 — The Hall of Fame rule — **done 2026-08-17, rule live, diff owed**

1. **Depends on *Archival results*** — `reported_player_count`,
   `attested_player_count()`, and the `"no_results"` eligibility guard. Without
   them the rebuilt HoF comes back empty (the floor rejects every reconstructed
   row) or, with a naive fallback, silently corrupts the international ranking.
   Consume `attested_player_count` for the 10-player floor; share
   `TWDA_MIN_PLAYERS` as a **constant**, never `_played_player_count`.
2. **`get_all_tournament_wins()`** replaces `get_tournament_wins_for_users`
   (`db.py:1288`). Drop the `user_uids` parameter entirely — enumerating winners
   from tournaments is the only way a legacy winner is ever seen. Keep the three
   existing boolean gates (`:1300-1308`), add the 10-player floor, the Limited
   exclusion, and the deck check as an `EXISTS` on `type='deck' AND
   tournament_uid = t.uid AND user_uid = t.winner AND deleted_at IS NULL` (both
   deck indexes already exist, `schema.sql:222-227`).
3. **`recompute_wins(user_uids: set[str] | None = None)`** as its own pass,
   reusing the no-change-guard shape from `ratings.py:306-316`. Then **remove
   the `user.wins = new_wins` write from `recompute_ratings_for_players`**
   (`ratings.py:304-316`) — that single line *is* the "membership turns on an
   unrelated coincidence" bug. Watch the regression it creates: today a fresh win
   updates `wins` via the finish-time rating recompute, so the optional user-set
   parameter must be wired into the finish and delete paths
   (`routes/tournaments.py:1136-1152`) or a new HoF entry waits for the nightly
   run.
   Leave a comment on the new predicate pointing at `ranking_eligibility` and
   noting that the divergence is **deliberate** — it is the point of the ticket —
   so a future reader doesn't "fix" it back into agreement.
   This stays server-computed: it is the same category CLAUDE.md already carves
   out for authoritative totals. Do not derive HoF client-side from the IndexedDB
   deck store even though the data is technically there.
4. **Move the >= 5 threshold out of the components**: one exported
   `HOF_MIN_WINS = 5` in `frontend/src/lib/tournament-utils.ts`, consumed by
   `rankings/+page.svelte:52` and `profile/+page.svelte:255`. Not into the engine
   (a PyO3/WASM entrypoint for an integer cutoff over a precomputed count fails
   KISS), and no denormalised `is_hof` boolean on `User`.
5. **Diff before flipping.** Compute new membership against the current 115 and
   review who drops out. 47 members sit at exactly 5 — 20% of the HoF is one win
   from the line, and a silent eviction is a support ticket with a name on it.

### Executed, and what is still owed on prod

Items 1–4 are in. `get_all_tournament_wins` (`db.py`) enumerates from the
tournaments and carries the whole rule including the deck `EXISTS`; the floor
runs in Python over `attested_player_count`, because the precedence chain and the
seat union are not expressible in SQL without duplicating the rule there.
`recompute_wins` (`ratings.py`) is its own pass, wired into the three tournament
paths, the archon import, the TWDA sync (after the deck pass) and the daily job;
`recompute_ratings_for_players` no longer touches `wins`.

**Item 5 is a prod step and is not done** — the diff needs the corpus. Capture
membership before deploying and again after the backfill; both sides come from
the shipped rule, so nothing restates it in a throwaway query:

```sql
SELECT "full"->>'name', "full"->>'vekn_id',
       jsonb_array_length("full"->'wins') AS wins
FROM objects
WHERE type = 'user' AND deleted_at IS NULL
  AND jsonb_array_length(COALESCE("full"->'wins', '[]'::jsonb)) >= 5
ORDER BY wins DESC, 1;
```

Personal data: it stays out of the repo. `backfill_twda.py` now runs a full
`recompute_wins()` before the snapshot so both directions settle in one pass —
otherwise the page grows on backfill day and shrinks at the nightly, one
migration reading as two incidents. Deploy → backfill → capture again.

## Phase 4 — Surfaces — **done 2026-08-17**

All five items landed, in `PlayerRecord.svelte` (mounted on `/users/[uid]` and on
`/profile` with `self`), the rankings caption, and the tournament page header.
Three things the build settled that the plan did not say:

- **Item 3 uses `attested_player_count`, not `description`.** The plan predates
  *Archival results* and proposed stamping "42 players" into free text. The count
  line it fixes renders only where `players` is present — i.e. member level, which
  is exactly where the attested size already reaches. Free text would have
  duplicated a fact that has a structured home, in untranslatable English, on
  every reconstructed row.
- **Both surfaces gate on `no_results`, not on the `twda` id.** The id survives
  `_adopt_same_event`, which overwrites a reconstruction with the full VEKN result
  set — badging that row archival would assert "the only surviving source" over a
  VEKN record, and reading its stale archive count over the VEKN roster would
  invert Settled decision 7. The badge takes the id *and* `no_results`; the count
  takes `no_results` and an attestation, matching what gates the write.
- **An unattested reconstruction shows no player count at all.** About a hundred
  archive entries carry no `players_count`, and `attested_player_count` then falls
  through to the winner's lone standing. "1 reported" is a worse answer than
  silence for an event whose size nobody recorded.
- **Item 4 cannot read `user.wins`.** The rule admits a win only *with* a deck, so
  the missing-decklist set is by construction disjoint from it. The prompt asks the
  local pair "you won it, no deck of yours is on it" — the same predicate
  `PlayerDecksSection` already nudges on per tournament, aggregated. It is not the
  Hall of Fame rule inverted, and deliberately does not filter on size or format:
  claiming eligibility client-side would re-derive the rule.
- **The deck archive renders without a `format`.** `DeckDisplay` validates against
  current legality, and a 2005 archive deck fails it for reasons its owner cannot
  act on.

1. `/users/[uid]` (219 lines, `PlayerRatings` only) gains the player's **win
   list and deck list** — both offline-first IndexedDB reads; the decks store
   already has a `by-user` index (`db.ts:242`) and `user.wins` is already
   tournament uids. Label it "Decks", never "all their TWDA decks", until
   coverage is complete.
2. **HoF page states its criterion** (one line under the title).
3. **Reconstructed events must read as archival.** A reconstructed row has one
   `Player`, so the tournament page renders "1 player registered"
   (`tournaments/[uid]/+page.svelte:913`) for an event that had 42. Put the real
   count and the provenance in `description` — free text, already in
   `_TOURNAMENT_PUBLIC_FIELDS` (`access_levels.py:165`), so no model change and
   visible at every level: *"Archival record reconstructed from the TWDA. 42
   players."* Badge the row as archival off `external_ids['twda']`, which is
   also already public (`access_levels.py:166`) — zero projection work, no new
   field.
4. **"This win is missing its decklist" prompt** on the player's own profile —
   this is what turns the gate into the encouragement the rule is for, rather
   than a retroactive penalty on wins finished before it ships.
   **Already unblocked**: the engine permits a post-finish deck upload when the
   player has none (`engine/src/tournament/mod.rs:2387` — `Finished` errors only
   `if existing_count > 0`), the frontend already allows it
   (`PlayerDecksSection.svelte:113`, "recovery"), and a winner nudge component
   already exists (`:198`, `m.decks_winner_nudge_self`). Only the profile-side
   surfacing is new.
5. New/changed strings → `i18n-translator`, 5 locales.

## Phase 5 — The push side — **done 2026-08-18**

Item 2 landed with the short event code line, which owns the replacement key.
Item 1 landed here, and went one step further than the plan: the emitted header
link is the **short form**, not the uid form, and `reconcile_twda.py` tier 1
parses `/t/<code>` against a `by_code` index. The plan's rationale for item 1 —
"krcg derives the entry `id` from the link" — is not quite how it works: the id is
the *file name*, which our submissions already key on the code. What the header
link actually buys is a second, independent anchor, and it costs nothing to make
it the form designed to be cited.

Decision 4 commits us to keeping the archive updated after decommission, and that
loop is now closed: nothing in the submission path reads a vekn event id.

**A non-numeric key needs no negotiation with the maintainer** — verified
2026-08-14 against `GiottoVerducci/TWD`, whose `decks/` directory already holds
`decks/0bbf344e-f63e-41bf-9b74-0fc82e91ae61.txt`, a UUID-named file among
otherwise numeric ones, which krcg parses normally (the Basagan ng Bungo 2025
entry). Worth telling him, not asking permission.

Deliverable 4 from the original ticket — archive-vs-pushed tracking beyond
per-tournament `twda_status` — is a genuinely separate feature; file it as a
child rather than carrying it here.

---

## Traps

- **`players_with_rounds` returns 0 for a reconstructed event** — the archive
  gives a count, a winner and a score but no roster, so neither branch of
  `engine/src/ratings.rs:73` finds anything, and the 10-player floor rejects
  every reconstructed win. Fixed by *Archival results* above, which is the
  dependency of Phase 3 — **and note the naive one-function fix is a trap that
  silently corrupts the international ranking**; read that section before
  touching `ratings.rs`. `twda_import.py` reads no `players_count` today.
- **`_adopt_same_event` will refuse a reconstructed row and create a duplicate.**
  While `vekn_tournament_sync` is still an upstream, its calendar scan can
  produce the vekn-linked copy of an event we already reconstructed; the adopt
  path declines any candidate with registered players and no rounds
  (`vekn_tournament_sync.py:411-417`) — exactly the reconstructed shape — so a
  fresh duplicate lands and only the end-of-run warning notices. **Teach it to
  adopt**: if the single candidate carries `external_ids['twda']` and has no
  rounds, adopt it. Overwriting its players/standings from vekn.net is *correct*
  — a full VEKN result set is strictly richer than a 1-player reconstruction. ~6
  lines, and it makes the reconstruction safe to land before `#579` instead of
  sequencing behind the whole decommission epic.
- **`external_ids` is overwritten wholesale** by the sync's full-rebuild branch
  (`vekn_tournament_sync.py:600-618` builds a fresh `Tournament` with the mapped
  `external_ids={"vekn": id}` from `:316`), so a `twda` key on a *vekn-linked*
  tournament is wiped on the next run. Round-less vekn-origin rows are precisely
  the class TWDA links to. One line, in the same constructor that already
  hand-preserves `checkin_code`/`twda_status`/`league_uid`:
  `external_ids={**existing.external_ids, **tournament.external_ids}`. The
  meta-only path (`msgspec.structs.replace`, `:529-546`) and `_adopt_same_event`
  (`:418`, in-place) are both already safe.
- **Drop the winner's `Player` row and three things break**: the winner renders
  as a **raw UUID** (`playerInfo` is built only from `players` and
  `rounds[].seating`, `tournaments/[uid]/+page.svelte:250-283`, falling back to
  printing the uid at `tournament-utils.ts:75`) on the tournament page, the
  social text and the copied results; the organizer roster is empty while the
  member view is populated (`PlayersTab.svelte:287` is `players`-driven,
  `PlayerView.svelte:612` is `standings`-driven); and the `wins` refresh never
  fires (`routes/tournaments.py:1140` seeds from `players`). It is also what
  makes the adopt-guard above meaningful. Non-optional — worth a regression test
  so it isn't refactored away.
- **Do NOT stamp `vekn_pushed_at`** on reconstructed rows, despite the ETL
  precedent (`migrate_from_archon.py:1251-1264`). It trips the delete guard at
  `routes/tournaments.py:1118-1122`, permanently blocking deletion of the entire
  reconstructed corpus — which is exactly where review errors will need cleanup —
  and collides head-on with `#574` (IC record curation). It also *means* "results
  came from or went to vekn.net", which is false here. `UNPUSHED_RESULTS_QUERY`
  (`vekn_push.py:429`) already excludes them (it requires a vekn id); the only
  real exposure is `UNCREATED_EVENTS_QUERY` (`:412`), which would happily create
  2005 calendar entries on vekn.net. Add
  `AND ("full"->'external_ids'->>'twda') IS NULL` to that query instead.
- **Don't exclude reconstructed rows from the duplicate tooling** — a genuine
  TWDA/vekn collision *should* surface. But `richness` (`dedup_tournaments.py:87`)
  ranks by play data, so a 1-player TWDA row always loses to a vekn copy: right
  for a true duplicate, destructive for a false pair produced by a generic name.
  The mitigation is upstream (Phase 0's denylist), not in the dedup script. Add a
  distinct report bucket so twda-keyed collisions read as their own class.
- **Never auto-delete on upstream disappearance.** Keying on the TWDA entry `id`
  is correct (it is the archive's own file key), but a renamed or removed entry
  leaves a `twda`-keyed row pointing at nothing. Log it into the same report
  bucket and let a human decide.
- **Reconstruction bypasses the engine, necessarily.** `FinishFinals`
  (`engine/src/tournament/mod.rs:2252`) is the only engine writer of `winner`,
  and `UpdateConfig`'s allowlist excludes `winner`/`players`/`rounds`/
  `standings`. These rows are a backend-side write, exactly as
  `vekn_tournament_sync` does it. Consequence worth naming: **there is no in-app
  way for a human to correct a reconstructed record afterwards** — see open
  decisions.
- `update_standings` no-ops when `rounds` is empty
  (`engine/src/tournament/standings.rs:154-157`), so injected standings survive
  a finish. Deliberate and load-bearing — do not "fix" it.
- Reconstructed rows must carry **no `league_uid`**: a one-row standings in a
  league yields league points off a zero coefficient
  (`leagues/[uid]/+page.svelte:170-178`).
- **Sizing to verify rather than discover in prod**: +~2300 tournaments across
  all three levels against a current ~30216 objects, roughly +22%. The public
  level gains ~2300 finished 2005-2013 events, landing in every anonymous
  visitor's snapshot. Check that the tournaments list's default view doesn't
  degrade with a decade of archival past events (client-side filtering only —
  CLAUDE.md forbids server-side pagination here) and the first-sync IndexedDB
  write cost on mobile.
- Trivial, fix in passing: `vekn_tournament_sync.py:653` cites
  `scripts/dedup_tournaments.py`; it is at `backend/scripts/`.

## Resolved since the plan was written (owner, 2026-08-14)

- **This ticket DOES owe an in-app correction path** for reconstructed records.
  Today nothing but a script can write `winner`/`players`/`standings`.
- **The TWD naming convention needs no negotiation** — see Phase 5.
- **Epic + children**, filed under this ticket.

---

# Archival results — shipped 2026-08-16

The field-and-guard change this epic was blocked on is in. What the remaining
phases can now rely on, in one place — the standing statement is
[tournaments](../wiki/tournaments.md), [vekn](../wiki/vekn.md#inbound) and
[hazards](../wiki/hazards.md):

- `Tournament.reported_player_count`, an externally attested field size, `0`
  meaning no attestation. Member projection, not public.
- `attested_player_count` over PyO3 and WASM: rounds, then the attestation, then
  the standings length. Feeds the rating coefficient and the win floors.
  `players_with_rounds` is unchanged and still answers who played.
- `ranking_eligibility` returns `"no_results"` where nothing was played, so an
  archival stub can never enter the rating set however large its attested count.
- `SetArchivalResults`, IC only, gated on `players_with_rounds(t) == 0`, refusing
  any row carrying `external_ids['vekn']` while the calendar sync is live. The
  lift is deferred in [vekn-decommission](../wiki/vekn-decommission.md).

**Phase 2.3 must stamp the field** from the entry's `players_count` on every row
it creates, and must not stamp anything else. Without it every reconstructed win
sits at an attested size of 1 and never clears the 10-player floor, which is the
whole point of the epic.

Two things measured while building it, that the later phases depend on and would
be expensive to re-derive:

- **There is no historic backfill.** All 3627 pre-2014 live tournaments are
  rounds-less, but every one carries scored standings, so `players_with_rounds`
  already returns a real number for the whole corpus. Only the ~1132 rows this
  epic creates need the field.
- **The size counter must not use the scored filter.** 580 pre-2014 events have a
  roster of 10 or more but fewer than 10 scorers; a floor reading the filtered
  count would stop counting their wins — 16% of the historic corpus. On standings
  length, 2660 clear the floor and zero rows are left short.
