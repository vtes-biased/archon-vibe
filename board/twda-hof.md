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

## Phase 0 — Event reconciliation — **matcher landed 2026-08-16, review outstanding**

`backend/scripts/reconcile_twda.py` is landed and read-only; the proposal table is
`board/twda-event-reconciliation.md`. **The reviewed decisions file does not exist
yet** — the 39 `review` rows are undecided, and Phase 2 must not run until an owner
has turned every one of them into `attach` / `create` / `skip`. The script writes
them into the TSV as `review` lines rather than omitting them, so a premature
consumer sees them and refuses instead of reading a short file as a complete one.
Several belong to Torstensson, Angseesing and Keeney — career counts this epic
exists to fix — so silently dropping them would defeat the ticket.

Against the live corpus:

| outcome | entries |
|---|---|
| attach — vekn id | 2177 |
| attach — winner + date (name-free) | 1174 |
| attach — winner + date + event name | 11 |
| attach — our own link | 1 |
| **create — no candidate** | **1136** |
| **review — needs a human** | **39** |

**The reconstruction is 1136 events, not the 2257 this plan sized it at.** The
"mostly linking, not importing" claim below is confirmed and then some, and the
review queue is 39 decisions rather than hundreds. The name-free tier measures
**99.9% precise at 94.9% recall** against the linked entries as ground truth.

Two design corrections the measurement forced, both already in the script:

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
- **The non-discriminating-name denylist below was not built, and is not needed.**
  It guards a name-keyed matcher; the shipped one never keys on a name, so a
  repeated or generic event name cannot produce a false match in the first place.
  What survives from that paragraph is the *display* obligation — a row named
  `tournament` is unusable in the UI, so Phase 2 still synthesizes a name from
  `place` + date at review time.

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

1. `event_link` → our own tournament uid — parse **both** the live
   `/tournaments/<uid>` form and the dead legacy `/tournament/<uid>/display.html`
   form. **Validate the uid resolves to a live tournament**; a stale or mistyped
   link must route to review, never fall through to name matching.
2. numeric `id` / `vekn.net/event/<id>` → `external_ids['vekn']` (today's path)
3. fallback: **a name-free match on date ± 1 day, winner name and country.**
   `find_same_event_tournaments` is *not* it — that query keys on the event name,
   which is the one field this corpus cannot use. It keeps the ± 86400s window and
   the country filter this tier also wants, which is why it read as the obvious
   precedent; the shipped matcher borrows those two rules and drops the name.

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

**And every one of the 3627 has zero rounds.** The archival shape is not something
the reconstruction introduces — it is the existing shape of the entire historic
corpus. See *Archival results* for what that costs Phase 3.

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

## Phase 1 — Winner identity (read-only, feeds the same decisions file)

The archive gives a name string and nothing else. 1552 distinct normalised
names.

**The bootstrap is the key insight.** 812 of the 1552 names appear in at least
one *linked* entry — an entry whose event we already hold with a resolved
`winner` uid. For those, the name → member mapping can be **read straight off
our own data**, with no name matching at all. That leaves **740 names needing
true matching, of which only 61 are HoF-relevant** (>= 5 entries). The top of
that list is recognisable veterans who stopped winning around 2013 — Erik
Torstensson (35), John Bell (29), Robyn Tatu (21), Rob Treasure (18), James
Messer (15).

So the review is tractable: a few dozen decisions that matter, not 1552.

1. Bootstrap the 812 from existing tournament winners. One name mapping to two
   different uids is a genuine homonym — flag it, never merge.
2. For the remaining 740, match the normalised name against `User.name`
   (`vekn_sync.py:558` builds it as `"firstname lastname"`, the same shape as
   the TWDA string), using the existing `_strip_diacritics` technique
   (`geonames.py:102`). Require a **unique** hit.
3. Country is a **tie-breaker, never a gate**: 107 of the 237 >= 5-entry names
   appear in more than one country and 46 have no country holding 80% of their
   entries — top players travel. `"Online"` is a pseudo-country in `place` and
   must not be read as one.
4. **Validate the matcher against the bootstrap before trusting it.** Run it
   over the 812 known-correct names and measure precision. That number decides
   whether auto-attach is safe at all, and it is free.
5. Emit `auto` / `ambiguous (N candidates)` / `unknown`, sorted by entry count
   descending so HoF-relevant names are reviewed first. Owner confirms; a
   handful of member creations may be approved for the genuinely unfindable.

**Entries whose winner never resolves are held OUT of the import**, in the
re-runnable queue — not imported winner-less. `Tournament.winner` is a user uid
and there is no winner-name field, so importing unresolved would mean a new
model field plus projections plus frontend fallback rendering. Worse, such a row
contributes nothing to the HoF (the rule needs a winner *and* a deck), renders
as an empty stub, cannot carry its deck at all (see Phase 2), and — having zero
players — becomes adoptable by `_adopt_same_event`, i.e. a live duplicate
magnet. What is lost is "the archive is complete" as a visible property;
mitigate with a counter in the report, not with orphan rows.

## Phase 2 — The sync

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

## Phase 3 — The Hall of Fame rule

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

## Phase 4 — Surfaces

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

## Phase 5 — The push side (in scope here)

Post-decommission **we cannot submit to the TWDA at all**: `submit_twda_pr`
keys the branch and file on the vekn event id (`twda.py:71-72`,
`archon/{id}` + `decks/{id}.txt`) and `maybe_submit_twda` skips with
`no_vekn_event`. Decision 4 commits us to keeping the archive updated after
decommission, so this closes the read/write loop the ticket is about and belongs
here rather than in `#579`. Two small changes:

1. Pass `https://archon.vekn.net/tournaments/{uid}` as `tournament_url` to
   `export_twda` instead of `""` (`routes/tournaments.py:357`). krcg derives the
   entry `id` from that link, so this is what makes Phase 0's first matcher tier
   useful — today we would be building a reader for a link we never write.
2. Rename `submit_twda_pr`'s `vekn_event_id` parameter to `event_key` and pass
   `tournament.external_ids.get("vekn") or tournament.uid`, then drop the
   `no_vekn_event` skip (`routes/tournaments.py:438`).

**The naming convention needs no negotiation — precedent already exists
upstream.** Verified 2026-08-14 against `GiottoVerducci/TWD`: the `decks/`
directory holds `decks/0bbf344e-f63e-41bf-9b74-0fc82e91ae61.txt`, a
**UUID-named** file among otherwise numeric vekn-event-id names, and krcg parses
it into the archive normally (it is the Basagan ng Bungo 2025 entry). So a
tournament-uid key is already accepted by both the repo and the parser; keying on
our uid post-decommission is a continuation, not a new convention. Worth telling
the maintainer, not asking permission. The only genuine defect is that that
file's header URL is the dead `display.html` form — our emitted URL must be the
live route.

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

# Archival results — the missing fact

The owner's instinct was that "a finished tournament we hold results for but no
per-round play data" is a real, unnamed thing (three producers already emit it:
`vekn_tournament_sync.py:215-321`, `migrate_from_archon.py:1066-1163`, and the
TWDA reconstruction here) and proposed formalising it as an explicit **mode** on
`Tournament`, with either a players list or just a count.

**Its scope is the whole historic corpus, not the reconstruction.** Measured on
prod 2026-08-16: **all 3627 pre-2014 live tournaments have zero rounds.** So
`players_with_rounds` returns 0 for every one of them, and the 10-player floor
rejects every pre-2014 win unless `reported_player_count` is **backfilled onto the
existing rows**, not merely stamped on the ~1136 reconstructed ones. Today
`get_tournament_wins_for_users` has no player-count gate at all, so those wins
currently do count: introducing the floor without the backfill would not shave the
47 members sitting at exactly 5, it would evict essentially the whole historic Hall
of Fame — including the three names in the done-condition. This makes *Archival
results* a hard prerequisite of Phase 3, not a parallel track, and makes Phase 3.5's
"diff before flipping" a certainty rather than a caution.

**Recommendation: add the missing fact, do not add the mode.** The gap is real
and is a hard blocker; the enum is over-modelling. Three reasons.

**1. The ~11 `len(rounds) == 0` sites are not one predicate — they are three,
and only one needs a new field.**

| what the site actually asks | sites | correct answer |
|---|---|---|
| "is there per-round detail to read?" | `ratings.rs:73`, `ratings.py:52-72`, `standings.rs:363-370`, `tournament-utils.ts:148`, `[uid]/+page.svelte:213,220` | `rounds.is_empty()` — already complete |
| "did these results originate here / is this copy richer?" | `vekn_push.py:429-438`, `vekn_tournament_sync.py:411-417` and `:492`, `migrate_from_archon.py:1548-1563`, `dedup_tournaments.py:87` | `external_ids` — already correct, and the fixes in *Traps* are already keyed that way |
| **"how big was the field?"** | `ratings.rs:73` returning 0 for a roster-less row | **nothing today — this is the gap** |

For the first group an enum changes `if rounds.is_empty()` into
`if results != Native`: identical code, except the enum **can lie**.
`rounds.is_empty()` is correct by construction; a persisted enum must be
maintained through reopen, `RestoreRound`, an archon import onto an existing row,
and `_adopt_same_event` overwriting a TWDA row with VEKN data. Six writers, and
one forgotten transition makes every downstream guard silently wrong.

**2. The field needs no backfill; the enum needs a risky one.**
`reported_player_count: int = 0` means "no attestation, behave exactly as today"
for all ~30k existing rows — no classification pass, no `explicit OR derived`
transition scaffolding. The enum requires retroactively classifying every
finished row, where a misclassification silently moves ratings.

**3. It must not touch the state machine.** `state` is in
`_TOURNAMENT_PUBLIC_FIELDS` (`access_levels.py:159`), so adding an enum value to
a synced field is a **breaking change for offline-first clients**: a PWA running
last week's bundle receives the new value over SSE, writes it to IndexedDB, and
falls through every `state === "Finished"` branch in `rankedStatus`, tab
derivation, the list and the calendar — silently. The general rule is recorded in
`wiki/sync.md#frontend-storage`.

## The shape

```python
# models.py Tournament
reported_player_count: int = 0
```

*Externally attested field size, when our roster is known to be incomplete or
absent. 0 = no attestation, derive as today.* Never written for natively-run
events — the engine already computes that correctly, and stamping it would create
a drift vector on reopen/rescore.

It covers the enum's whole job: has-round-detail stays `rounds.is_empty()`;
roster-completeness falls out as `reported_player_count > len(players)`, which
*already* applies to VEKN imports (they silently drop players whose VEKN id we
don't hold, `vekn_tournament_sync.py:222-224`); is-archival for the UI is
`state === "Finished" && !rounds?.length`, or the `external_ids['twda']` badge in
Phase 4.3.

Per producer: VEKN sync → `len(data["players"])`; archon ETL round-less → the old
count; TWDA → `players_count`; native → 0.

**Name it `reported_player_count`, never `player_count`.** `engine/src/league.rs:53`
already reads `tournament["player_count"]` from a caller-*synthesized* summary
(built at `leagues/[uid]/+page.svelte:177`); a real model field of that name would
silently satisfy that read with different semantics.

**Projection: public**, alongside `open_rounds` (`access_levels.py:172`) and for
the same reason — `rankedStatus` reads it and must not lie to anonymous viewers.

## The trap this replaces (and the bug in the first draft of this plan)

The earlier version of this plan said "fix `players_with_rounds` to fall back to
a stored count" **and** "the row is floor-ineligible for ratings, so zeros are
harmless". Those contradict each other, and the first one is actively dangerous.
Walk it: `ranking_eligibility` (`engine/src/ratings.rs:53-68`) tests
`open_rounds` → `players_with_rounds < 8` → `has_final`. With a naive fallback a
TWDA row scores count=20 and passes `has_final` (a non-empty `winner` already
implies one, `ratings.rs:63`) → **`eligible`**. It then enters the eligible set at
`ratings.py:252`, its winner gets a `TournamentRatingEntry` with vp=0/gw=0, and
`tournament-utils.ts:349` badges ~2300 archival stubs as **Ranked**. That is
silent corruption of the international ranking, shipped by a change described as
making the badge honest.

**Two functions, not one:**

```rust
fn players_with_rounds(t) -> usize            // unchanged: eligibility + prelim scoring
pub fn attested_player_count(t) -> usize {    // new: floors that measure event SIZE
    max(players_with_rounds(t), t["reported_player_count"])
}
```

plus an explicit guard at the top of `ranking_eligibility`: **no rounds and no
scored standings → `"no_results"`**. Then the HoF's 10-floor consumes
`attested_player_count`, ratings keep `players_with_rounds`, and `rankedStatus`
correctly reads Unranked for an archival stub. The "zeros are harmless" claim in
Phase 2.3 is true *because of* that guard, not automatically — do not remove it.

**The HoF floor and the TWDA floor then use different counters.** The rule above
says the HoF uses "the TWDA floor (`TWDA_MIN_PLAYERS`)" — that means the
**constant**, not the function: `_played_player_count`
(`routes/tournaments.py:369`) is rounds-only *and* subtracts `non_competing`
proxies, so wiring it in would return 0 for every archival row. Share the
constant, never the function.

## Four implementations of the count rule — the cleanup this ticket earns

Beyond the Rust/Python twin there are two more, with a *third* definition:

- `routes/tournaments.py:369` `_played_player_count` — rounds-only, minus proxies
- `frontend/src/lib/tournament-utils.ts:311-329` `playedPlayerUids` /
  `seatedPlayerCount` — and this one feeds **client-side league standings**
  (`leagues/[uid]/+page.svelte:170-200`), so league RTP depends on a TS
  reimplementation of a Rust rule
- `routes/tournaments.py:1989` uses bare `len(tournament.players)` as
  `player_count` in the archondata/report payload — a fifth reading, wrong for
  every import

Expose `attested_player_count(t_json) -> i32` over PyO3 + WASM in
`engine/src/lib.rs` and delete the arithmetic in `ratings.py:75` and
`tournament-utils.ts:328`, keeping the set-returning helpers (enumeration, not
rule). Leave `_played_player_count` but comment the deliberate divergence. The
`player_count` name-collision hazard is in `wiki/hazards.md`.

## The in-app correction path

**An engine event, not a backend route, and IC-only.** The reason is not offline
support — nobody corrects a 2007 record in a basement — but that a backend route
would be the **fourth** non-engine writer of `winner`/`players`/`standings`, and
unlike the three batch importers it is interactive and repeatable. Batch ETL
bypassing the engine is a defensible one-off; a user-facing edit form doing it is
business logic creeping into Python. There is already an invariant a third writer
must not re-break (the winner-must-have-a-`Player`-row rule in *Traps*, whose
violation prints a raw UUID); in the engine it is enforced once.

`SetArchivalResults`:

- Payload `{winner, players: [uid], reported_player_count}`. **Deliberately not
  `standings`** — they are contractually prelim-only and we have no prelim data;
  keep the zeros.
- Guard: reject unless `state == Finished && rounds.is_empty()`. That single gate
  makes it structurally impossible to touch a natively-run event — and note it is
  again a *data-shape* gate, not a mode flag.
- Guard: `reported_player_count >= len(players)`; auto-materialise the winner's
  `Player{state: Finished, finalist: true}` and matching `Standing`.
- New explicit `EngineError` variants per the error-codes contract.
- **Authz: IC only**, predicate in `engine/src/permissions.rs` beside
  `can_delete_sanction`. Not organizer — TWDA reconstructions have empty
  `organizers_uids`, and for VEKN imports the organizer is whatever upstream
  claimed. VEKN 8.6 invalidation authority is IC's anyway.
- **Refuse rows carrying `external_ids['vekn']` while the VEKN sync is live.**
  `vekn_tournament_sync.py:492`'s full-rebuild branch fires whenever
  `not existing.rounds and tournament.players`, so an IC correction to a
  vekn-linked round-less row is wiped on the next nightly run, silently and
  permanently. One line; lift it after `#579`. (The alternative — a
  `results_corrected_at` marker the sync respects — is a second field for a
  capability that expires with `#579`.)
- Check that an archival row cannot be taken offline
  (`permissions.rs:816 can_take_tournament_offline`) — pointless and a
  lock-orphan risk.

Bonus of this shape: the `_adopt_same_event` fix in *Traps* gets simpler and
safer — adopting a TWDA row and overwriting it with VEKN data needs no mode flip,
because `rounds` becomes non-empty (or stays empty with a real roster) and every
derivation self-corrects.

## Rating coefficient — explicitly out of scope here

Stamping `reported_player_count` on existing VEKN imports is honest and cheap,
but **do not wire it into `compute_rating_points`'s coefficient in this ticket.**
If you did, every finalist in a partial-roster import gains points, the 18-month
top-8 window reshuffles, and rankings visibly move. That is a separate, measured
change. Also note `TournamentRatingEntry.player_count` (`models.py:201`) is
embedded in every entry, so a changed count re-saves and re-broadcasts every
affected `User` — bulk it like Phase 2.6 if it ever happens.

Verified unmoved by the field: `UNPUSHED_RESULTS_QUERY` (`vekn_push.py:429`)
stays rounds-keyed, dedup `richness` stays play-data-keyed, league standings move
only if the coefficient is wired.
