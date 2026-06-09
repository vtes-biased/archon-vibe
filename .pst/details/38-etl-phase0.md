# Phase 0 ETL — archon → archon-vibe (#38)

Deliverables (built 2026-06-09, dry-run validated against a full prod dump):

- `backend/scripts/migrate_from_archon.py` — the ETL. Reads the OLD archon DB,
  writes the NEW `objects` table + `auth_methods`, **reusing the backend's own
  `save_*` helpers** so access projections (public/member/full) are computed
  identically to runtime.
- `backend/scripts/migrate_validate.py` — ETL integrity harness (count parity,
  orphan-ref scan, projection sanity, semantic invariants, random spot-checks).
- `backend/scripts/run_vekn_sync.py` — standalone VEKN member+tournament sync
  runner (mirrors `main.run_vekn_sync`) for the post-ETL merge / rehearsal.
- `backend/scripts/check_merge.py` — `--snapshot` the ETL baseline, then `--check`
  after VEKN sync to assert the merge added no dupes and wiped no archon data.

## Merge prep (ETL-first → VEKN sync, see #35 "Data flow")

The migration is ETL-first, then VEKN sync reconciles on top. The ETL therefore
sets up the data so the existing VEKN sync merges cleanly:
- maps old `extra.vekn_id` → `external_ids["vekn"]` (8,328 tournaments) so the
  tournament sync MATCHES instead of duplicating;
- sets `local_modifications={"roles"}` on users with roles (551) so the member
  sync can't strip archon-assigned Judge/Ethics/Rulemonger/PTC/PT/Judgekin;
- creates Discord `AuthMethod`s only — legacy passwords aren't migrated (see below).

Two production-code fixes were required for a clean merge / wheel deploy:
- `vekn_tournament_sync.py` — on an existing match it rebuilt the Tournament with
  ONLY vekn fields, **wiping `rounds`/`finals`/`standings`**. Now: if the
  tournament has play-data (`rounds`/`finals`), refresh vekn metadata ONLY and
  preserve play-data; round-less vekn-origin imports keep the full refresh. (Latent
  data-loss bug independent of migration.)
- `geonames.py` — loaded data via a hardcoded `files("backend.src.data.geonames")`.
  The wheel installs the package as top-level `src` (`pyproject packages =
  ["backend/src"]`), so `backend` doesn't exist there → `No module named 'backend'`
  in beta/prod. Now anchors on `files(__package__)` (matches `db.py`'s `schema.sql`
  pattern). The current modern importlib.resources API; legacy `read_text(pkg,name)`
  helpers are deprecated since 3.11 (no subdirectory support).

## Rehearsal — full path on the real vekn.net API (PASSED, 2026-06-09)

Empty DB → ETL → `run_vekn_sync.py` (live API) → `check_merge.py`:
- member sync: 0 created / 18,669 updated / 162 unchanged / **0 errors** (18,831 total)
- tournament sync: 6 created / 7,546 updated / 537 unchanged / **0 errors** (8,089 total)
- merge invariants: no dup `vekn_id` (18861/18861), no new dup vekn-event-id (gap
  15=15, pre-existing in old archon), **rich rounds preserved 267→267**,
  **protected roles intact 109→109**, discord auth untouched (629), 0 orphans,
  **30,957 objects decode clean**.

## Dry-run sandbox

Prod dump `archondb.dump.gz` (repo root) loaded into a throwaway Docker PG17:

```
docker run -d --name archon-etl -e POSTGRES_PASSWORD=etl -e POSTGRES_USER=etl -p 5544:5432 postgres:17
# create role archon + DBs archon_old (load dump) / archon_new (apply backend/src/schema.sql)
cd backend
OLD_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_old \
NEW_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_new \
uv run python scripts/migrate_from_archon.py --truncate
uv run python scripts/migrate_validate.py --samples 40
```

## Prod data profile (from the dump)

| table | rows | notes |
|---|---|---|
| members | 19,003 | ~4× the plan's "~5k" estimate |
| tournaments | 8,371 | Finished 8,239 / Planned 94 / Registration 35 / Finals 2 / Playing 1 |
| leagues | 17 | |
| member_deletions | 635 | → soft-deleted user shells |
| tournament_events | 36,442 | NOT migrated (dump-only, #36) |
| **clients** | **0** | **no OAuth integrations to migrate** (re-register moot) |
| formats | — | Standard 7,700 / Limited 642 / V5 21 / **Draft 8 → Limited** |

Two tournament shapes: ~263 **rich** (round detail + finals as last round) and
~8,100 **thin** (historical imports: aggregate results + winner, no rounds).

## Migration run result (full)

19,003 users + 635 shells, 8,371 tournaments, 17 leagues, 64 sanctions,
2,861 decks, 1,354 auth methods (725 email / 629 discord). ~42 s locally.

## Validation result — PASSED (0 hard failures)

- Count parity exact (users/leagues/tournaments/sanctions/decks).
- 0 orphan references (player/winner/sanction/deck → user/tournament).
- Every object has a `full` projection.
- Semantic invariants: standings VP == prelim seat VP (finals excluded); prelim GW
  obeys the engine rule (0 violations); no public deck on an unfinished tournament;
  `decklists_mode` (19) and `standings_mode` (65) non-defaults preserved.
- 50/50 random tournaments: players, winner, finalist count, and per-player
  prelim+finals gw/vp/tp aggregate all match old archon exactly.
- **Round-trip: all 30,951 objects decode back into their msgspec models (0 fails).**

## Scores & standings — preserved, not recomputed (verified correct)

Old archon's stored seat scores were verified correct and are **preserved as-is**:
- Across all prod prelim seats, 0 GW-rule violations (gw=1 ⟺ vp≥2 ∧ sole table max).
- Finals GW (winner gets 1, seed-tiebroken, no 2VP floor) matches the engine's
  `compute_gw_finals` rule exactly.
- Per-player `player.result` == sum of stored seats (no internal inconsistencies).

The real historical bug was in the **vekn-push** path (it folded finals VP/GW into
prelim scores), not the DB. The new model structurally prevents this: the ETL writes
prelim-only `standings` (sum of prelim seats) and prelim+finals `Player.result`,
keeping the two separated. League scoring (`league.rs`) adds finals on top of the
prelim standings, so standings MUST stay prelim-only.

(An earlier draft recomputed scores via `engine.compute_gw`; that was wrong because it
applied the prelim sole-leader rule to finals tables. Preserving the verified-correct
source values is simpler and avoids re-implementing engine logic. `compute_gw_finals`
is not exposed to Python — if a future full-recompute is ever wanted, expose it first.)

## Mapping reference (implemented)

- roles: Admin→IC, Playtester→PT, others identical (unknown → warn+skip)
- format: Draft→Limited; rank: Grand Prix→BASIC (no GP rank; GP lives in league mode)
- tournament state: Finals→Playing (no FINALS state)
- sanction level: Caution/Warning/Disqualification→same, Ban→suspension
- sanction category: old 9-value enum → new JG-v2 category(+subcategory); unknown → procedural_error
- sanctions deduped by uid across member.sanctions ∪ tournament.sanctions (64 distinct)
- standings = prelim-only (sum of preserved prelim seats); Player.result = prelim+finals;
  finalist from `finals_seeds` membership; winner from old `winner`
- decks: monodeck `player.deck` (round=None) always; per-round seat decks only when
  `multideck`; `public` set per `decklists_mode` policy at finished tournaments;
  `attribution=None` (anonymous — old archon never recorded designer-credit consent)
- `decklists_mode` / `standings_mode` preserved from source
- league `ranking`→`standings_mode`; `judges`→`organizers_uids`; `sponsor`→`coopted_by`
  (verified: old `sponsor` is always a user_uid)
- skipped & recomputed post-import: `ratings`, `ranking`

## Known limitations (acceptable / source-bound)

1. **Finals seed ORDER** is preserved only for rich tournaments (lives in
   `FinalsTable.seed_order`). Round-less imports have no finals-game data — only
   finalist *membership* (`player.finalist`) + winner are preserved. Faithful to source.
2. **5 members have a password but no email** → no email auth method created
   (can't, no identifier). They retain discord auth if any; else re-register.
3. `tournament.extra` → `external_ids` is a best-effort flat copy (scalar values only).
4. **Ratings** are not migrated — recomputed from tournament results post-import
   (Phase 2). Rating verification (vs old stored ratings) is deferred to that step.
