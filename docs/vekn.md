# VEKN integration

How the app talks to vekn.net, to the TWDA, and to the legacy archon database. The
organization and its rules are [domain](domain/vekn.md); this is the plumbing. What
retiring these syncs means is [below](#decommission); the evidence for the work waiting on it is
[vekn-decommission](vekn-decommission.md).

## Feature flags

| Flag | Scope | Effect |
|---|---|---|
| `VEKN_PUSH` | backend env | enables outbound member creation push |
| `VITE_VEKN_PUSH` | frontend env | shows the amber pending-sync badges on unsynced members |
| `VEKN_SYNC_ENABLED` | backend env | enables periodic inbound member roster sync |
| `VEKN_SYNC_INTERVAL_HOURS` | backend env | inbound period from 04:00 UTC, default 6h |
| `TWDA_SYNC_ENABLED` | backend env | enables the archive sync — separate from `VEKN_SYNC_ENABLED`, because it must outlive the VEKN API |
| `JUDGE_SYNC_ENABLED` | backend env | enables the daily [judge directory](#judge-directory) sync — a different upstream with no credentials |
| `VEKN_PUSH_INTERVAL_HOURS` | backend env | outbound member push period, default 1h |

All VEKN member sync directions need `VEKN_API_BASE_URL`, `VEKN_API_USERNAME`,
`VEKN_API_PASSWORD`.

**Beta runs inbound member sync and no outbound write, by design.** `VEKN_PUSH` is
false there, and the TWDA GitHub App credentials are left unset so `is_configured()`
is false and every archive submission skips. Neither vekn.net nor the public
archive may take a write from a rehearsal environment — that is what makes beta
safe to run a production script against. Its corpus is **not** a mirror of
production and answers no question about production's row counts: the scripts
rehearsed there have been applied there.

## Outbound push

Real-time member pushes are `asyncio.create_task` and never block a user request. The
member is saved with `vekn_synced = false` before the task runs, failures are log-only,
and the hourly batch retries every member with `vekn_synced = false`. On success,
`push_member` sets `vekn_synced = true` and SSE-broadcasts the updated member so clients
see the change without reconnecting.

Tournament calendar and results push retired at [Stage 1](#decommission).

### Push constraints

- **A `vekn_id` is required to *register*, not merely to push.** The engine refuses
  to seat a player without one (`Register`, `AddPlayer`, and the `CheckIn` walk-in
  path all reject an empty id), so an official sponsors or links the account before
  the player is added. That is stricter than [rules §9.6](domain/tournament-rules.md#sanctioning-and-reporting),
  which only excludes placeholder-numbered results from the ratings. Offline play is
  the exception: it mints local `TEMP-` ids, and go-online resolves each against a
  real account — by VEKN id, then by email — or creates a member. Which is why
  taking a tournament offline needs `sponsor_member` on top of organizer rights.
- **Member creation requires a city.** The registry refuses a create whose
  `firstname`, `lastname`, `email`, `country` or `city` is empty — `state` is the
  one optional field, per its own `createPlayer` in `vekn-api/vekn/registry.php`
  — and the tournament desk form that mints most members never asks for a city.
  `push_member` sends the country capital in place of an empty one; the roster
  sync writes that city back on its next pull, so the local row ends up holding
  it too. A member with no country cannot be pushed at all and keeps its amber
  pending-sync badge.
- **A member the registry already knows under another id is never pushed.**
  `createPlayer` refuses a create whose email, or whose full name as a substring,
  matches an existing player, and names that player's `veknid`, always a different
  id from ours, since a taken id is refused first. It means we minted an id for
  someone vekn.net already registered, and inbound sync has usually brought their
  registry record in as a second local account. vekn.net is the source of truth,
  but the push does not heal it: the unique `vekn_id` index refuses moving the
  registry id onto our member, keeping our id under the registry's name is a false
  sync, and a substring match can name a different person. The failure line carries
  the registry's id, and an IC reconciles the two accounts by hand.

### Outage resilience

The app keeps working through hours or days of vekn.net downtime and self-heals on
recovery: local saves and the SSE broadcast always precede the push, and the next
hourly batch drains the backlog. On top of that:

- **Fail-fast** — the batch aborts the whole run on the first
  `VEKNAPIConnectionError` (transport down, timeout, or auth failure) rather than
  re-timing-out every pending member serially at 30–120s each; it reruns next cycle.
  Per-member *data* errors still skip just that member. The client wraps aiohttp total
  timeouts into that exception, because **a `ClientTimeout` breach raises
  `asyncio.TimeoutError`, not an `aiohttp.ClientError`** — an
  `except aiohttp.ClientError` misses timeouts entirely.
- **No lost updates** — `push_member` re-fetches the User immediately before writing
  back `vekn_synced`. The batch loads rows up front but may save minutes later during
  outage-recovery backlog, so re-fetching narrows the clobber window to microseconds
  and interim edits survive.
- **Observability** — scheduled jobs record last success and error in process, and
  `GET /admin/vekn-status` (IC-gated) exposes member sync, TWDA sync, judge sync and
  batch push, so a days-long outage is visible without grepping logs. It resets on
  restart. The batch's `errors` counts every member push that did not land, refused or
  skipped, so a stuck item reads as non-zero every hour. Every such failure logs one
  line, `VEKN push failed: member=<vekn id> reason=…`, which the production dashboard's
  **VEKN push** table groups over the last two hours: the list to reconcile by hand
  when the refusal is a registry collision.

## Inbound sync

### Members

`VEKNSyncService` pulls the full roster and reconciles:

- Creates Users for unknown VEKN IDs, **seeding roles at creation only** — Prince
  and NC from the upstream `princeid`/`coordinatorid`, IC from a static roster.
  This is a bootstrap seed, not a transcription of legacy archon's role history.
  Judge ranks are **not** seeded: vekn.net has no field for them, and the
  [judge directory](#judge-directory) is their source.
- Updates identity — name, country, city, state — for existing members. **The
  state disambiguates the city** in GeoNames before the most populous of that
  name wins, so Newark, Ohio does not land in New Jersey (gh-76).
- **Never re-writes roles on update.** A member created by this sync before the
  legacy ETL ran keeps only its bootstrap seed, and the ETL's richer role data
  never lands for that member. This is the intended end state: roles are
  app-managed and archon is the system of record for them.
- Infers `coopted_by` relationships, only where the field is unset — or names no
  user row, as the legacy import left behind — and not in
  `local_modifications`. A member goes to the official with the **longest**
  matching `vekn_prefix`, so a Prince whose prefix extends their NC's keeps their
  own members. A sponsor already recorded is never replaced by a prefix guess:
  the legacy record wins.
- Non-destructive: fields recorded in `local_modifications` by the profile and user
  edit routes are never overwritten.

Tracking fields on User: `vekn_synced`, `vekn_synced_at`, `local_modifications`.

Manual trigger: `POST /admin/sync-vekn` (members).

Inbound tournament sync retired at [Stage 1](#decommission). Existing rounds-less VEKN
imports stay in the corpus as imported; `backend/scripts/dedup_tournaments.py` resolves
historical duplicate pairs by soft-deleting the loser and transplanting `external_ids.vekn`
(and any archive key as `twda_entry`) onto the survivor.

## TWDA

### Outbound

`twda.py` opens or updates a GitHub pull request against the
[TWDA repo](https://github.com/GiottoVerducci/TWD) from a fork we own — every write
lands there, the archive granting only permission to open the pull request
([dev](dev.md#configuration)) — idempotent on branch
`archon/{event_code}` and file `decks/{event_code}.txt`, create-or-update, with the
short event link in the PR body and in the deck header krcg parses back as the
entry's `event_link` — which is what makes an entry we submitted resolvable against
its own tournament on the next archive read. The commit and the pull-request title
read `Add TWD` for a new file and `Update TWD` when the branch already held one. It
fires on the finish action; on any later action on the Finished event that moves
the winner or a winner's deck — the post-finish pass
([tournaments](tournaments.md#engine-event-catalog)), so late uploads, owner
corrections and a rescored final all reach the archive, the open pull request
taking the new file and a merged one getting a fresh request; on a config edit
of the Finished event that moves its country or online flag, the header's place,
while its pull request is still open;
and on go-online for a
tournament finished offline. In a multideck event the archived deck is the one
stamped at the finals index; none on record is `no_deck`.

Every attempt records its outcome on `Tournament.twda_status`: `submitted` with the
PR URL, `skipped` with a reason code — no winner, Limited format (draft and sealed
decks aren't archived), Storyline format (a deck can only be there from a
pre-switch format, outside what the archive describes), reconstructed from the
archive (`external_ids['twda']`, whose event code is the archive's own file key —
[hazards](hazards.md#consumers-that-must-move-together)),
no rounds on record (a rounds-less import, whose header could state no `NR`),
fewer than 10 players by `attested_player_count` — proxies count, as they do for
the rating — unranked per the engine's
`ranking_eligibility` (the same predicate as the ranked badge — the championship
rank axis never gates TWDA), no event code yet, no place (neither a country nor
the online flag, which would publish an empty place line — setting one submits),
GitHub App unconfigured, or the winner has no deck — or `failed`, whose reason is
`step[:http-status]`: the call that failed (`deck`, `config`, `auth`, `fork_sync`, `fork_ref`, `branch`,
`commit`, `pull_request`, or `internal` for an unexpected error) and what the API
answered. It is organizer/full projection only and shows as a status line on the
finished-tournament organizer view, which names the failing step and offers the
re-save retry **only** for a transient answer — 5xx, 408, 429, or no status at
all except `config`. A 4xx is a refusal and an unreadable App key a
misconfiguration: both repeat identically, so neither offers the retry.

**Header**: the archive's own convention, which its maintainer reviews against —
the date in US form with no time (`August 29th 2026`, ` -- <end>` for a multi-day
event), `Online` as the place of an online event, the player count as
`attested_player_count` — the field that played, never the registered roster with
its no-shows — `NR+F` or `NR (no final)`, and the event link directly under the
winner's name. An in-person event's place is the archive's `City, Country`, the
city its GeoNames name ([tournaments](tournaments.md#configuration)); an event that
predates the field and was never given one still publishes its country alone. Then
a score line,
`-- 1GW4.5 + 3vp in final`: the winner's **standings** row, which is prelim-only,
with the finals seat's VP beside it — never the aggregated `result`, which already
folds the final in and would read to the archive as a double count. It is the
archive's most common wording.

**An update keeps the archived header's event name and place lines** whenever the
archive already holds the file: the maintainer rewrites them on nearly every merge
— venue and city on 38 of the first 44, the name on 7 — and a full rewrite would
revert that work on every correction. The date line is kept too, unless it is
still in the ISO form this bot first wrote, which the maintainer wants replaced by
ours. Format, count, winner, link, score and deck stay ours. So a later edit of
the event's name, place or date reaches an open pull request but never a merged
entry, and an update that changes nothing past the kept lines commits nothing: the
status links the archived file instead of a pull request.

**The header is only as good as krcg's reading of it.** The archive is consumed
through krcg's TWDA parser, and ours through it again on the next archive read, so
a header krcg cannot read is a header lost: it reads the date **only** in the US
form, and an ISO date — the bot's first `2026-06-21 09:00:00`, or a hand
normalisation to `2026-06-21` — leaves the event, its date, place, player count
and link unread, the winner falling into the comment. The header test parses our
export back through krcg rather than matching strings.

**Comments**: the deck's comment sits verbatim under the name and credit, ahead of
the crypt. What a deckbuilder
leaves behind when a text list is imported into it — the lines it could not parse
land in its description, which a deck-link import copies into `comments` — is
stripped **once, at that import**, by `strip_deckbuilder_noise` (engine): the player
sees and edits exactly what will publish, and a comment typed in the app is never
touched. It matches shapes, never a language's vocabulary, and biases to keeping:

- a **leading block** is dropped only when it holds three or more markers:
  `Key: value` fields (a key of one to three words, a value of at most six —
  `Nombre del mazo:`, `Date:`, `Location:`) and section lines (one or two words,
  then a bracket opening on a count of at most three digits — `Cripta (12 cartas,
  …)`, `Master (14)`). Every restated header carries three or more; two are a
  player's (`Strategy: …` over `Tech: …`, `Won Nationals (1st)`), and so is
  anything past the first line of prose;
- a leading `descr…` field counts as a marker, closes the block and, when the
  block goes, keeps its value without the label — it is the description another
  deckbuilder held;
- anywhere, a TWDA score line (`— 2GW8 …`); a bare `[YYYY-MM-DD]` revision stamp,
  a bracket missing on either side, unless the next non-blank line is text not
  opening on a stamp itself — then it dates a note the player typed under it;
- a rule of `=`, `-`, `_`, `*`, `~` or `#` only ahead of the body's first text:
  past it, it is a player's separator or the close of a block they marked.

It is idempotent. Card lines that did not resolve (`1 Khadija Al-Kindi`) survive:
telling them from prose would take the card map.

**Designer credit**: the winner's name is always in the header; a separate optional
`Created by: <name>` line is emitted only when the deck is credited to someone
else — a `Member` credit resolved to that member's current name, or the name a
past `Archive` credit carries. Names only, never VEKN IDs. A credit that
names nobody, an `Anonymous` or `Owner` one and a `Member` id no member holds
alike, emits no line and no fallback: the typed credit keeps no loose string for
one to fall back to. The winner's name appearing regardless is intentional — the
TWDA is the public win registry, which is also why anonymity never withholds the
winner's own `user_uid` ([tournaments](tournaments.md#engine-event-catalog)). Privacy never
reaches the submission either: the winner's deck publishes whatever its owner
chose, and the TWDA holds no other. A winner has no opt-out, and none is built until
a member asks for one.

### Inbound

**The VEKN record outranks the archive.** Where both describe the same event, the
historical VEKN result stands and the TWDA sync fills only what the record does not
carry (city and winning decklist). The
concrete consequence is that `reported_player_count` is stamped **only where
`players_with_rounds` is zero** — no rounds and no standings row carrying a score,
which is the archival reconstructions and nothing else — and **never on a VEKN
import**, even though the retired sync dropped players whose VEKN id we did not hold
and its `len(data["players"])` would be a truer field size than the roster that
survived. Stamping those would move a live rating: the count feeds
`compute_rating_points`' coefficient, the window is a rolling 18 months, and the
winner and runner-up of every partial-roster import inside it would gain points. The
archival rows cannot, being decades outside that window.

The same predicate gates the write and the read — `attested_player_count` reaches
the field only where nothing else answers — so the attestation can never contradict
a record we hold.

`twda_import.py` reads `static.krcg.org/data/twda.json` and does two things:
reconstructs the historic events the archive is the only record of, and gives every
resolved winner their decklist (an `Owner` credit — the archive's `player` is
the winner — `public=True`, only where the winner has none for that tournament).
Then it recomputes those winners' Hall of Fame lists, which is why that step
follows the deck pass rather than preceding it:
a reconstruction only counts once its deck is on record
([the rule](tournaments.md#configuration)). The backfill depends on the ordering
too — it regenerates the snapshot immediately afterwards, and a win list computed
later would miss it. It runs on `twda_sync`, **its own job under
its own flag** and recorded on the vekn-status panel: a different upstream, no VEKN
credentials, that outlives the VEKN API.

**The archive's place names the city.** A reconstruction takes its city from the
entry's `place`, and settling an attach fills an empty one the same way: read right
to left, since the archive writes `Venue, City (STATE), Country` as often as
`City, Country`, each segment matched in GeoNames within the place's country. A
name GeoNames splits by region, `Springfield (Illinois)`, takes the region the place
names — the `(STATE)`, a US code spelled out — before the most populous. On entries
dated 2025 or later, `Palma de Mallorca, Spain` is ignored because legacy archon
filed unrelated events against placeholder venue 3800 (*GoblinTrader Mallorca*) and
the archive copied that place onto them.

**The scheduled run only ever does a delta.** More than `MAX_CREATES_PER_RUN`
unsettled entries pending means it is standing in for the initial backfill, so it
writes none and logs an error naming `backfill_twda.py` — which lifts the cap and
suppresses broadcasting. Without that, the first scheduled run after a deploy *is*
the backfill, at four thousand SSE frames per connected client. Decks still land
for everything already resolved, so a capped run is useful rather than refused.

**It resolves nothing at runtime, and it settles what it resolves.** An entry the
corpus already answers for is read off the corpus; only what is left is looked up
in `backend/src/data/twda_decisions.tsv`, a reviewed mapping shipped in the wheel:
`attach` names one of our tournaments, `create` names the winning member and asks
for a reconstruction, and anything else is counted and skipped. A wrong
reconstruction mints a duplicate event and credits a real person with a win they
did not take, so the file is the gate and there is no fallback path around it. An
applied `attach` **stamps the archive key onto the event it named**, and a settled
row knows its own winner, so the file is never read for that entry again. It is an
extract of uids taken on one day against one database: re-reading it forever is
what made a target that moves under a dedup transplant or a re-migration stop
attaching, silently and for good.

**The two archive keys are not interchangeable.** `external_ids['twda']` means
*reconstructed from the archive*, is written only by the reconstruction, and six
readers turn on it: `resolve_event_code` and the event-code backfill, the Hall of
Fame's no-attestation grandfather, the duplicate report's refusal to propose, the
tournament page's archival badge, and the TWDA submitter's `reconstructed` skip. A
settled attach carries `external_ids['twda_entry']` instead — *this event is the one
that entry describes* — which gates only the TWDA sync's own recognition. Reusing
`twda` would move all six at once, most concretely admitting rounds-less imports to
the Hall of Fame and handing them the archive's file key as their public event code.

**A stale-target warning names only a decision that never applied**, since one
that did is on the corpus and never re-read. What remains points at a tournament
this database does not hold — a uid from another environment, or one that moved
before it was ever read. Its mirror is the orphan warning: a row holding an
archive key the archive no longer carries. Neither is auto-repaired.

**No ETag.** There was one, and it is gone deliberately: once identities come from
a reviewed file, *our* side moves while the archive sits still — a member is
created, renamed, or claims a VEKN id — and a 304 would skip the reconciliation
forever, silently and permanently. A 12 MB fetch against a static CDN every cycle
is the cheaper half of that trade.

The reconstruction writes the same rounds-less archival shape the historical VEKN
and archon imports produced, plus the attested `reported_player_count`
([tournaments](tournaments.md)).

**That key reaches only half the archive.** The TWDA began carrying vekn event
links around 2013, so of 4538 entries 2211 are linked and 2327 are not — 2257 of
them dated before 2014. The unlinked half is a **linking gap, not an event gap**:
our corpus reaches back to 2004 and holds most of those events already, imported
from legacy archon with no vekn id. Reconstructing them blind would mint about a
thousand duplicates.

`backend/scripts/reconcile_twda.py` resolves the archive against the live corpus
and is **read-only** — it has no `--apply`. It writes the decisions file above;
human decisions go the other way, into `backend/src/data/twda_rulings.tsv`, which
is an *input* to it. That split is what keeps the generated file safe to
regenerate: rulings are never re-derived and a re-run never clobbers a decision.

**A ruling is checked against the database being reconciled before it is emitted.**
Its target is a uid, which is an identity claim about one corpus; run against
another it names nothing, and emitting it unchecked writes a decision that can
never apply. An event ruling whose tournament this database does not hold is
emitted as `review`; a winner ruling whose member it does not hold holds the name
out rather than fall through to the matchers, which are what the human overruled.
Both are counted on the run's own output.

It answers two questions per entry. **Which event** — four tiers: an `archon.vekn.net` link in `event_link`; the vekn
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

**And which member won it** — the archive gives a name string and nothing else.
Strongest first: the *bootstrap*, which reads the answer off our own data (an entry
that attaches hands over that tournament's resolved winner, no name matching at
all, and is also the only honest scoring set for everything below it); an exact
normalised-name match on a name exactly one member holds; surname-anchored classes;
and a whole-name fuzzy match that must clear a floor, clearly beat the runner-up,
and agree on the surname. The surname-anchored classes refuse a surname more than
`MAX_SHARING_SURNAME` members share — there the given name carries the whole claim,
and that is where the one wrong match in the bootstrap sat. `--validate` scores
both halves and names any class the bootstrap never exercised, because an
unmeasured class is not a proven one.

**A vekn event id is not proof of identity.** An organizer can submit an entry
under an id they later abandoned, leaving ours holding the empty husk. A
disagreeing winner name does not by itself unseat the id — our names are routinely
fuller than the archive's (`Javier Naranjo Ortiz` vs `Javier Naranjo`), and 75
entries disagree that way harmlessly — only a rival event on the same date won by
the same player does.

**The two `event_link` url forms quote uids from two different id spaces.** The
live `/tournaments/<uid>` form quotes ours; the legacy
`/tournament/<uid>/display.html` form quotes the uid legacy archon minted, which
the import kept in `external_ids['archon']` on 255 rows. Resolving a legacy link
against our own uid space alone reports it dead, and the entry then falls to a
reconstruction it does not need. The app redirects the legacy form:
nginx proxies it to the backend, which 301s to the live event holding that uid and
404s any other.

**One winning deck per event means two entries cannot share a tournament.** Each
tier judges a single entry, so a collision between two of them is invisible until a
pass over the whole verdict set; the weaker tier's claim yields, a tie yields both,
and the loser is an event we genuinely do not hold. Without that pass one win is
attached to the wrong tournament and the other is never recorded at all.

## Judge directory

**The VTES Exams public judge directory is the sole source of Judge and Sheriff**
([domain](domain/vekn.md)). `judge_directory.py` reads
`www.vtesexams.com/api/v1/judges/` — public, no credentials, 60 requests a minute
per IP — daily at 05:30 UTC as `judge_sync`, its own job under its own flag,
recorded on the vekn-status panel and runnable from the admin panel.

The directory is exhaustive for the app: a valid Elder entry makes the member a
Judge, a valid Neonate or Ancilla entry a Sheriff, and any other holder of either
role loses it — unlisted, or listed past `valid_until`. Rulemonger is never
touched. Matching is by VEKN id; a listed id no member holds is logged and
reported, never created. Every write goes through `accounts.save_member`, so the
Discord Judge Level follows.

The request carries the last ETag, and a 304 **still reconciles** from the cached
body: our side moves while the directory sits still — a validity date passes, a
member gains a VEKN id. A failed fetch writes nothing, and an empty directory is
refused rather than read as everyone's revocation.

`backend/scripts/preview_judge_sync.py` prints what a run would change, writing
nothing. Applying is the admin panel's run, never a script: the Linked Roles push
is a background task a script process would exit before.

## Legacy archon sync

**Retired 2026-08-24.** Legacy archon is decommissioned: the `archon_web` unit,
the daily merge timer and the `archondb` database are gone from the VPS, and
archon-vibe is the only stack on it. What follows is the record of how the corpus
we hold was built, and it still governs `--merge`, which survives for a restored
dump.

`backend/scripts/migrate_from_archon.py` has two modes sharing the mapping code:
an **insert-only ETL** (default; `--truncate` wipes first) for beta rebuilds and
disaster fallback, and an **idempotent `--merge`** that ran daily through the
parallel run, with old archon as a read-only second upstream. Cutover was freeze,
final merge, vhost swap. The runner was a systemd timer, not an in-app job.

**Where the archive is.** Three artefacts, each held both on the prod box and
off-box on the maintainer's machine:

| File | On prod | What it is |
|---|---|---|
| `archondb-final-<stamp>.dump` | `/var/backups/archondb-final/` | the database as legacy left it, restore-verified at 39,475 `tournament_events` rows |
| `tournament_events-<stamp>.dump` | `/var/backups/archondb-final/` | that table alone — the one thing the new schema has no equivalent for, archived rather than migrated |
| `archondb-premigration-<stamp>.dump` | `/var/backups/archondb-premigration/` | the older original, taken from the PG16 cluster before it was dropped |

**Those two directories are deliberately outside `/var/backups/postgres`.**
`pg-backup.sh` deletes every `*.dump` older than `RETENTION_DAYS` in its own
backup dir — including dumps of databases that no longer exist, which is exactly
what these are — so an archive stored there erases itself a week later. The
corollary is that nothing manages them either: they are not pruned, and **not
pushed off-box by restic**, which covers only `/var/backups/postgres`. The
off-box copies are the durable half.

The frozen restic repo `archon-db-backups/archondb` held every daily dump taken
up to the drop — 54 snapshots, 952 MiB, the last of them 2026-08-24 — and since
the database was gone nothing ever pruned it. It was deleted on 2026-09-02,
redundant against the three artefacts above. The bucket now holds `archon` and
`globals` only, so a *"repo has no backed-up database"* warning in the nightly
log names a **new** orphan and is worth acting on.

**Single writer per field**, which is what prevents a daily flip-flop between
syncs:

| Data | Writer |
|---|---|
| identity — name, country, city, state | VEKN sync |
| contact, nickname, discord, community links | archon sync |
| `coopted_by` | archon sync, VEKN sync inference (fills an unset or dangling sponsor), an official's edit |
| roles | nobody — seeded once by whichever creates the row first, app-managed thereafter |
| sanctions, leagues | archon sync, upsert by source uid |
| rich play data — rounds, seatings, decks, finals | archon sync |
| `local_modifications` fields | nobody — local edits trump both syncs |

`coopted_by` carries extra rules. Within the archon sync `remap_coopted_by` is its
sole writer, running once the full uid map is known, and an **unresolved sponsor is
never written** — legacy refs dangle and rotate uid nightly, and chasing them
rewrote ~10k users every night, all re-downloaded by every client at its next
reconnect. Outside the syncs it is stamped when a member is minted — sponsor,
create, or an organizer's registration issuing the id.

**An official's edit pins it.** IC, or the member's NC, sets the sponsor to any
live VEKN member or clears it (`PATCH /users/{uid}/sponsor`), and the field joins
`local_modifications` either way: both syncs then leave it alone, so a cleared
sponsor stays cleared instead of being re-inferred. Setting keeps `coopted_at` —
the official corrects who, not when; clearing drops it. An account merge takes
the sponsor from whichever side is pinned, the survivor first.

`coopted_by` is member-visible, `coopted_at` full-only: who sponsored a member is
already public through the id prefix and vekn.net's registry, and it is what the
members directory's Mine filter matches against the viewing official.

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
pre-run `pg_dump` for recovery; and merge writes are **not** live-broadcast over SSE,
so clients catch up on their next reconnect.

## Decommission

The end state is **archon as the system of record** for members, events and results,
with vekn.net frozen as a historical archive.

**Push is not a third direction to decide — it *is* API calls**, so each direction's
push dies with the read it accompanies.

### Stage 1 — the tournament calendar retired (2026-11-24)

BCP removed the legacy `www.vekn.net` event calendar, event creation and event
management pages. Inbound tournament sync (`sync_all_tournaments`) and outbound
event/results push are retired; Archon is the system of record for events and
results. The hourly batch keeps running for members until stage 2. The app computes
its own ratings, and every tournament limitation the calendar sync imposed — 2–4
round cap, post-push round immutability, frozen `rank`/`format`/`start`/`proxies`,
the VEKN-footprint delete block, the vekn-linked guard on `SetArchivalResults`, and
deferred `event_code` stamping — is lifted.

The historical corpus curation unblocked by this stage sits in
[vekn-decommission](vekn-decommission.md).

### Stage 2 — the member roster retires, when vekn.net registration closes

`VEKNSyncService` stops, along with member creation push (`VEKN_PUSH` /
`VITE_VEKN_PUSH`) and `audit_cities.py`, which reads the roster. It is sequenced
second because member identity is load-bearing in a way the calendar is not — the
engine refuses to seat a player without a `vekn_id` — and because only the officials
review waits on it.

**The precondition is a registry precondition, not a technical one.** We already
allocate ids ourselves — `allocate_next_vekn_id` takes the first gap in *our own*
corpus and `push_member` tells vekn.net the number rather than asking for one — so
the roster sync's remaining job is picking up members who registered on vekn.net
directly. While that form is open and we are no longer reading, two registrars mint
into one namespace and collide. Closing it is what makes the stage safe; a reserved
range for us was the alternative and costs a negotiation plus a change to the
allocator, for no gain once vekn.net is an archive.

### What survives

The TWDA sync, on its own flag and its own schedule, with no VEKN credentials — it
is a different upstream and is the sole external source of historic wins (candidate
for retirement once no non-Archon TWDA submission route remains). Submission to the
archive survives on the short event code.
