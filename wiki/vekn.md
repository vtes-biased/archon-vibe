# VEKN integration

How the app talks to vekn.net, to the TWDA, and to the legacy archon database. The
organization and its rules are [domain](domain/vekn.md); this is the plumbing.
Work deferred until these syncs retire: [vekn-decommission](vekn-decommission.md).

## Feature flags

| Flag | Scope | Effect |
|---|---|---|
| `VEKN_PUSH` | backend env | enables all outbound push |
| `VITE_VEKN_PUSH` | frontend env | restricts the `max_rounds` UI to 2–4, shows the VEKN link badge and the amber pending-sync badges |
| `VEKN_SYNC_ENABLED` | backend env | enables periodic inbound member and tournament sync |
| `VEKN_SYNC_INTERVAL_HOURS` | backend env | inbound period, default 6h |
| `VEKN_PUSH_INTERVAL_HOURS` | backend env | outbound push period, default 1h |

All directions need `VEKN_API_BASE_URL`, `VEKN_API_USERNAME`,
`VEKN_API_PASSWORD`.

## Outbound push

Real-time pushes are all `asyncio.create_task` and never block a user request. The
object is saved with the flag unset before the task runs, failures are log-only,
and the hourly batch retries off the unset flag. Each function SSE-broadcasts the
updated object after saving so clients see the change without reconnecting.

| Trigger | Flag set on success |
|---|---|
| tournament create | `external_ids["vekn"]` |
| tournament finish | `vekn_pushed_at` |
| member sponsor / create | `vekn_synced = true` |

**Batch retry**, hourly, catches every missed real-time push: members with
`vekn_synced = false`; tournament events with no `external_ids.vekn`; tournament
results with `vekn_pushed_at IS NULL` **and a non-empty `rounds` array**.

The `rounds` guard excludes round-less VEKN imports — an import carries summary
results only, and re-pushing the source of record is pointless. Rich ETL and
archon-merged history does have rounds, so both importers stamp `vekn_pushed_at`
on every finished tournament they write, old archon having already pushed those
results. The engine invariant that standings are non-empty exactly when rounds are
is what makes this guard safe.

A successful results push here also retries the TWDA submission for events that
missed it at finish — finished offline, or whose VEKN event id only arrived in the
same batch.

### archondata format

```
{nrounds}¤{rank}§{first}§{last}§{city}§{vekn}§{gw}§{vp}§{vpf}§{tp}§{toss}§{rtp}§...
```

GW is prelim-only, with the finals GW removed for the winner, and `vp` is prelim
with `vpf` separate — see the double-count warning in
[domain](domain/vekn.md#never-chase-veknnets-stored-rtp).

Format and rank map to a VEKN event type id: Standard/Basic 2, Standard/NC 8,
Standard/CC 6, Limited/Basic 3, V5/Basic 16.

### Push constraints

- `max_rounds` is immutable once pushed, enforced backend and frontend.
- VEKN requires a name of 3–120 characters, 2–4 rounds, and an organizer holding a
  `vekn_id`.
- **A `vekn_id` is required to *register*, not merely to push.** The engine refuses
  to seat a player without one (`Register`, `AddPlayer`, and the `CheckIn` walk-in
  path all reject an empty id), so an official sponsors or links the account before
  the player is added. That is stricter than [rules §9.6](domain/tournament-rules.md#sanctioning-and-reporting),
  which only excludes placeholder-numbered results from the ratings. Offline play is
  the exception: it mints local `TEMP-` ids, and go-online resolves each against a
  real account — by VEKN id, then by email — or creates a member. Which is why
  taking a tournament offline needs `sponsor_member` on top of organizer rights.
- The organizer is impersonated via a `Vekn-Id` header on `create_event`, so the
  calendar entry is filed under the **organizer's own** VEKN id.
- Open-rounds events are never pushed.

### Outage resilience

The app keeps working through hours or days of vekn.net downtime and self-heals on
recovery: local saves and the SSE broadcast always precede the push, and the next
hourly batch drains the backlog. On top of that:

- **Fail-fast** — the batch aborts the whole run on the first
  `VEKNAPIConnectionError` (transport down, timeout, or auth failure) rather than
  re-timing-out every pending item serially at 30–120s each; it reruns next cycle.
  Per-item *data* errors still skip just that item. The client wraps aiohttp total
  timeouts into that exception, because **a `ClientTimeout` breach raises
  `asyncio.TimeoutError`, not an `aiohttp.ClientError`** — an
  `except aiohttp.ClientError` misses timeouts entirely.
- **No lost updates** — push functions re-fetch the User or Tournament immediately
  before writing back the vekn flags. The batch loads rows up front but may save
  minutes later during outage-recovery backlog, so re-fetching narrows the clobber
  window to microseconds and interim edits survive.
- **Observability** — scheduled jobs record last success and error in process, and
  `GET /admin/vekn-status` (IC-gated) exposes member sync, tournament sync and
  batch push, so a days-long outage is visible without grepping logs. It resets on
  restart.

### Post-push divergence

The results push is **write-once**: once successfully pushed, vekn.net cannot be
updated or corrected through the API, so a post-push correction never reaches it.
Resolving that means a manual admin fix on vekn.net, out of band.

`vekn_results_stale` is a sticky flag set when result-bearing content — `winner`,
`standings`, `finals`, `rounds` — changes after `vekn_pushed_at`. It is detected by
**content diff, not event type**, in both places results can change post-push: the
tournament action handler (a reopen and rescore) diffs all four before and after,
and the sanction handler (an SA- or DQ-driven recompute) diffs standings. Both skip
the compare once already stale, so it fires at most once per pushed tournament.

It is excluded from the member projection, re-stamped from the authoritative row at
go-online, has no in-app clear path, and surfaces to organizers as an "Out of sync
with vekn.net" header badge — shown regardless of `VITE_VEKN_PUSH`, unlike the
amber pending-sync badges, which are flag-gated.

## Inbound sync

### Members

`VEKNSyncService` pulls the full roster and reconciles:

- Creates Users for unknown VEKN IDs, **seeding roles at creation only** — Prince
  and NC from the upstream `princeid`/`coordinatorid`, IC from a static roster.
  This is a bootstrap seed, not a transcription of legacy archon's role history.
  Judge ranks are **not** seeded: they are app-managed with no vekn.net field to
  derive them from.
- Updates identity — name, country, city, state — for existing members.
- **Never re-writes roles on update.** A member created by this sync before the
  legacy ETL ran keeps only its bootstrap seed, and the ETL's richer role data
  never lands for that member. This is the intended end state: roles are
  app-managed and archon is the system of record for them.
- Infers `coopted_by` relationships.
- Non-destructive: fields recorded in `local_modifications` by the profile and user
  edit routes are never overwritten.

Tracking fields on User: `vekn_synced`, `vekn_synced_at`, `local_modifications`.

### Tournaments

`sync_all_tournaments()` imports historical events:

- Standings are **prelim-only** — the project contract. When a final was played
  (`sum(vpf) > 0`) it reconstructs a `finals` object — seats by placement, winner
  GW 1, seat VP = `vpf` — so rating and league add finals on top, matching the
  shape of a native or ETL-imported tournament. A summary-only winner with no
  `vpf` instead gets the tournament-win GW from the engine's rating rule, with no
  finals object.
- Re-sync compares the authoritative play data so a VEKN-side score correction, and
  legacy folded imports, self-heal.
- **Authority follows content.** VEKN is authoritative for a matched event only
  where it has something to say: a local row *with* rounds, or an incoming event
  with no players, gets a metadata-only refresh. Rebuilding a round-less row from
  an empty calendar entry used to reset an in-app event still taking registrations
  back to `Planned` and discard everyone registered — on every sync until its first
  round started.
- **Event times are wall clock at the venue**, which is how `start`/`finish` are
  stored: naive, paired with `timezone`. The sync writes VEKN's time verbatim and
  fills `timezone` from a guess off the venue country and city; online events with
  no venue keep the UTC default. Converting to UTC here made every reader that
  anchors the naive value shift it twice.
- Carries `proxies_allowed` onto `proxies`, **except under a championship rank,
  which forbids proxies by rule**. A few vekn.net championships do set the flag,
  and importing that combination would block every later config edit on engine
  legality. The calendar entry is create-only with no update endpoint, so the flag
  is owned by vekn.net: the sync refreshes it like other descriptive metadata, and
  the app's field is frozen once a tournament holds a vekn id.
- Seeds venue autocomplete data.
- Stamps `vekn_pushed_at = now` on finished imports so the batch never re-uploads
  them.
- Rebuilds changed tournaments field by field, so local-only bookkeeping
  (`checkin_code`, `twda_status`) must be **explicitly carried over** from the
  existing row or it resets on every re-sync.

Each phase — member, tournament, TWDA — is wrapped independently: an exception or
timeout logs an error and skips that phase for the cycle without aborting the
others.

### Matching an incoming event

The primary key is `external_ids.vekn`. The legacy archon merge imports old events
that never carried a vekn id, though, and those are invisible to that key — each
path used to insert its own copy of one real event. So on a miss the sync falls
back to **name + start within 24 hours** and *adopts* the local copy, stamping the
vekn id onto it rather than creating a second row. The two paths get their times
from different humans and the observed skew reaches 9 hours. The legacy merge
applies the same fallback as its last key.

**Name + day is not an identity key.** Legacy imports share placeholder names —
`Imported VTES Event` covers hundreds of distinct 2005 events, dozens on a single
Saturday — and one convention runs several same-named events in a day. It is
evidence of identity only where it is *unique in the corpus*, so both callers
abandon the match when it isn't: the sync refuses if any other same-name,
same-day copy already holds a vekn id (proof the key doesn't discriminate there),
the merge refuses on more than one candidate, and a declared `country` that differs
drops a candidate outright. The sync additionally refuses a candidate holding
registered players but no rounds, because the round-less update path treats
vekn.net as authoritative for players and adopting would wipe a live registration
list.

Duplicates that already exist are **reported, not repaired**: each run ends with
one grouped query logging live copies of one event where **some but not all** hold
a vekn id. That mixed condition is what makes the report mean anything — without
it, every same-name, same-day cluster matches and the output is mostly distinct
events. Copies that *all* hold different vekn ids are a separate class: one event
entered twice on vekn.net, which is VEKN's record to reconcile, not ours.

Resolve a reported group with `backend/scripts/dedup_tournaments.py`. It reports
the play-data metrics the choice hangs on — the vekn-linked copy is often the
*poorer* one — then soft-deletes the losers and **transplants the vekn id onto the
survivor**. Without that transplant the next sync finds no live holder of the event
id and re-creates the copy just deleted. Ratings aggregate whatever is live, so a
group with more than one rating-eligible copy was double-counted: recompute after
applying.

Manual triggers: `POST /admin/sync-vekn` (members and tournaments),
`POST /admin/sync-vekn-tournaments`.

## TWDA

### Outbound

`twda.py` opens or updates a GitHub pull request against the
[TWDA repo](https://github.com/GiottoVerducci/TWD), idempotent on branch
`archon/{vekn_event_id}` and file `decks/{id}.txt`, create-or-update. Five triggers
fire it: the finish action; a winner-deck upsert on an already-finished tournament,
by an organizer or by the winner adding their *first* deck, so late uploads and
post-event edits reach the archive; the manual organizer publish; the batch after a
successful results push, covering events finished offline or whose VEKN event id
only just arrived; and go-online for a tournament finished offline, which usually
records an immediate skip since the event isn't pushed yet, with the batch retrying
once it is.

Every attempt records its outcome on `Tournament.twda_status`: `submitted` with the
PR URL, `skipped` with a reason code — no winner, Limited format (draft and sealed
decks aren't archived), fewer than 10 players played, unranked per the engine's
`ranking_eligibility` (the same predicate as the ranked badge — the championship
rank axis never gates TWDA), no VEKN event id, GitHub App unconfigured, or the
winner has no deck — or `failed`. It is organizer/full projection only and shows as
a status line on the finished-tournament organizer view.

**Designer credit**: the winner's name is always in the header; a separate optional
`Created by: <name>` line is emitted only when the deck is attributed to someone
else. Names only, never VEKN IDs. The winner's name appearing regardless of
attribution is intentional — the TWDA is the public win registry.

### Inbound

**The VEKN record outranks the archive.** Where both describe the same event, the
VEKN result stands and the TWDA fills only what the record does not carry. The
concrete consequence is that `reported_player_count` is stamped **only where
`players_with_rounds` is zero** — no rounds and no standings row carrying a score,
which is the archival reconstructions and nothing else — and **never on a VEKN
import**, even though the sync drops players whose VEKN id we do not hold and its
`len(data["players"])` would be a truer field size than the roster that survived.
Stamping those would move a live rating: the count feeds `compute_rating_points`'
coefficient, the window is a rolling 18 months, and the winner and runner-up of
every partial-roster import inside it would gain points. The archival rows cannot,
being decades outside that window.

The same predicate gates the write and the read — `attested_player_count` reaches
the field only where nothing else answers — so the attestation can never contradict
a record we hold.

`twda_import.py` pulls winner decklists from
`static.krcg.org/data/twda.json` and creates decks for matched tournaments, running
inside the VEKN sync after tournament sync and before the rating recompute. Recent
entries match by numeric `id` = `external_ids["vekn"]`, older ones by VEKN ID in
the event link. It creates a deck only when the winner has none for that
tournament, with `attribution="twda"` and `public=True`. The ETag cache is
in-memory only and the ~12 MB JSON is released after parsing.

**That key reaches only half the archive.** The TWDA began carrying vekn event
links around 2013, so of 4538 entries 2211 are linked and 2327 are not — 2257 of
them dated before 2014. The unlinked half is a **linking gap, not an event gap**:
our corpus reaches back to 2004 and holds most of those events already, imported
from legacy archon with no vekn id. Reconstructing them blind would mint about a
thousand duplicates.

`backend/scripts/reconcile_twda.py` resolves the archive against the live corpus
and is **read-only** — it has no `--apply`. Its output is a decisions file a human
reviews and the reconstruction later consumes; unreviewed entries are skipped,
never created. Four tiers: an `archon.vekn.net` link in `event_link`; the vekn
event id; a **name-free** match on date ± 1 day, winner name and country, with the
event name and then the **roster length** breaking a tie; then a reconstruction
candidate. That length is `len(players)`, not any of the four "how many played"
implementations [hazards](hazards.md) indexes — it is a matching confirmer only and
never reaches a rating or a floor. Neither the name nor the count is a key — 869
pre-2014 rows are named `Imported VTES Event`, and the count is absent on 100
entries of the archive and collides freely across the corpus —
while winner name resolves half the unlinked corpus at 99.9% precision, measured
against the linked entries. As a *tie-break* the count is decisive, because the
archive and the archon row agree on it exactly for most of the multi-event weekends
the tier otherwise stalls on.

**A vekn event id is not proof of identity.** An organizer can submit an entry
under an id they later abandoned, leaving ours holding the empty husk. A
disagreeing winner name does not by itself unseat the id — our names are routinely
fuller than the archive's (`Javier Naranjo Ortiz` vs `Javier Naranjo`), and 75
entries disagree that way harmlessly — only a rival event on the same date won by
the same player does.

**The two `event_link` url forms quote uids from two different id spaces.** The
live `/tournaments/<uid>` form quotes ours; the dead legacy
`/tournament/<uid>/display.html` form quotes the uid legacy archon minted, which
the import kept in `external_ids['archon']` on 255 rows. Resolving a legacy link
against our own uid space alone reports it dead, and the entry then falls to a
reconstruction it does not need.

**One winning deck per event means two entries cannot share a tournament.** Each
tier judges a single entry, so a collision between two of them is invisible until a
pass over the whole verdict set; the weaker tier's claim yields, a tie yields both,
and the loser is an event we genuinely do not hold. Without that pass one win is
attached to the wrong tournament and the other is never recorded at all.

## Legacy archon sync

`backend/scripts/migrate_from_archon.py` has two modes sharing the mapping code:
an **insert-only ETL** (default; `--truncate` wipes first) for beta rebuilds and
disaster fallback, and an **idempotent `--merge`** run daily during the
parallel-run period, with old archon as a read-only second upstream. Cutover is
freeze, final merge, vhost swap. The runner is a systemd timer, not an in-app job.

**Single writer per field**, which is what prevents a daily flip-flop between
syncs:

| Data | Writer |
|---|---|
| identity — name, country, city, state | VEKN sync |
| contact, nickname, discord, `coopted_by`, community links | archon sync |
| roles | nobody — seeded once by whichever creates the row first, app-managed thereafter |
| sanctions, leagues | archon sync, upsert by source uid |
| rich play data — rounds, seatings, decks, finals | archon sync |
| `local_modifications` fields | nobody — local edits trump both syncs |

`coopted_by` carries an extra rule: `remap_coopted_by` is its sole writer, running
once the full uid map is known, and an **unresolved sponsor is never written** —
legacy refs dangle and rotate uid nightly, and chasing them rewrote ~10k users
every night, all re-downloaded by every client at its next reconnect.

**Tournament matching** in merge mode, at most one live tournament per vekn event
id: by uid → idempotent update; else by `external_ids.archon` or
`external_ids.vekn` → merge rich data INTO the vekn-created copy, whose uid
survives, and a round-less incoming copy never overwrites a rich original; else
insert under the old archon uid. Both-rich behaves differently by path: on the
vekn/name paths it is a one-app-per-event violation, logged loudly and skipped;
on the uid and `archon`-marker paths it is an intentional overwrite — a
legacy-run event is rich on both sides mid-parallel-run and old archon owns it
until it finishes there. The `archon` marker, recorded whenever a rich payload
merges into a vekn-created copy, is the echo guard letting a later run recognize
its **own** merge rather than mistake it for a both-rich conflict — its absence
wiped a live event on 2026-08-03 (Open de Coya 2026, vekn 13412).

**VEKN-less legacy participants** — legacy archon never enforced a VEKN id at
registration, so the merge resolves the survivors through fixed uid-keyed lists
bounded by the production dump, deliberately not a general algorithm. A player
with **no round seating** is a registration artifact: dropped wholesale
(`KNOWN_DROP`), or dropped from a single tournament's players when the account
plays elsewhere (`KNOWN_DROP_IN_TOURNAMENT`). One who **actually played** must
resolve to a real account: `KNOWN_REMAP` onto the member's real VEKN id, or a
fresh VEKN id allocated and marked push-eligible so the batch push claims the
number on vekn.net before a future vekn.net assignment can collide with it.

Other invariants: deterministic deck uids (uuid5 of tournament + user + round); a
pre-run `pg_dump` for recovery; merge writes are **not** live-broadcast over SSE,
so clients catch up on their next reconnect; and `vekn_pushed_at` is stamped on
merged finished tournaments so the batch never re-uploads them.
