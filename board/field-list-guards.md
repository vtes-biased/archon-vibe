Doc-impact: wiki/hazards.md ("Fields silently dropped" shrinks to what remains
unguarded; delete the stale cooptation-inference line at hazards.md:19-20 —
`_infer_coopted_by` mutates in place since `d044027`), wiki/testing.md (record
the guard tests next to the access-levels trap note).

# Field-list drift guards — per-site survey

Model kinds: backend models are `msgspec.Struct` (`msgspec.structs.fields(X)`),
route bodies are Pydantic v2 (`X.model_fields`), the engine Tournament is
untyped `json::JsonValue` (only the hand-written `config_fields` array),
frontend types are erased TS interfaces (no runtime enumeration). The repo has
**zero** exhaustiveness tests today; `test_engine_model_contract.py` is the
nearest pattern in spirit (pins enum drift, not field sets).

## Derive (the list collapses into a loop)

1. **go-online server-wins re-pull** — `routes/tournaments.py:2428-2443`, seven
   hand-copied assignments with three coercion variants. Collapses to
   `for name in SERVER_OWNED: request.tournament[name] =
   msgspec.to_builtins(getattr(tournament, name))` — `to_builtins` handles the
   datetime/Struct cases uniformly. Note the neighbors: `organizers_uids` is
   server-wins but merged (`:2423`), and `offline_*` + `modified` are stamped
   after (`:2445`) — the frozenset covers only the replace-wholesale seven.
2. **VEKN sync `_update_user`** — `vekn_sync.py:601-651`, a 7-field literal
   repeated three times (locals, `has_changes`, write-back). The field set is
   already runtime data (`vekn_data.keys()` from `_map_vekn_to_user`); collapse
   to a `getattr`/`setattr` loop. Code shrinks.
3. **`/action` copy block** — `routes/tournaments.py:1380-1436`, 30 hand-written
   `if` lines below `TournamentActionRequest` (`:1337`). Replace with
   `{"type": request.type} | request.model_dump(exclude_none=True,
   exclude={"type"})` **plus an explicit truthy-only set** — nine fields use
   truthy guards on purpose (`user_uid`, `player_uid`, `display_name`,
   `scores`, `comment`, `status`, `seating`, `label`, `pool`; e.g. `winner=""`
   must reach the engine to clear, `label=""` must not). Each of the nine needs
   the guard style confirmed, not assumed. `vekn_id` stays absent from the
   model (server-injected); the derivation must not reintroduce it. Pydantic's
   default `extra="ignore"` is the silent-drop mechanism — an undeclared key
   still vanishes; the guard here is the derived copy, not a 422.
4. **Detach split** — `accounts.py:201-267`, two `msgspec.structs.replace`
   kwarg lists. They are not complements: `modified`, `calendar_token`,
   `local_modifications` appear in both; ~9 fields (name, country, city,
   city_geoname_id, state, deceased_*, uid, deleted_at) appear in neither and
   stay on both copies. So the single source is a **three-way classification**
   (PERSONAL / UID_KEYED / SHARED) asserted exhaustive against
   `structs.fields(User)`, with a small exception map for values msgspec
   defaults can't supply: `calendar_token` (carried to the personal account,
   nulled on the record), `uid` (fresh uuid7). Existing behavioral tests:
   `test_account_surgery.py:245,:330`.

## Pin (exhaustiveness test)

5. **Member projection denylist** — `access_levels.py:137-142`
   (`_TOURNAMENT_MEMBER_EXCLUDE`, 4 names). The rule ("organizer-only secret?")
   is a judgement, not derivable — so introduce the currently-implicit
   `MEMBER_VISIBLE` set (~45 names) and assert
   `visible ∪ excluded == structs.fields(Tournament)`, forcing a new field to
   be classified. `wiki/testing.md` designates `test_access_levels.py` as the
   one home for projection-membership assertions — the test goes there. The
   User side is allowlists (fail-safe) and needs nothing.
6. **Config field set** — four copies with no shared source:
   `CreateTournamentRequest` (`routes/tournaments.py:796`), the Python
   `Tournament(...)` literal (`:927`), the engine create literal
   (`engine/src/tournament/mod.rs:159`), the engine `config_fields` array
   (`:2420`, 26 strings, applied `:2448`). Export the array over PyO3 (a
   ~3-line getter in `lib.rs`) and write one Python test comparing it against
   `structs.fields(TournamentConfig)` minus the non-config fields and against
   `CreateTournamentRequest.model_fields`. **Live gap to close while here:**
   `table_rooms` is in `config_fields`, `TournamentConfig` and the TS type but
   in neither create path — add it to both create paths (currently only
   `TableRoomsEditor` writes it via `UpdateConfig`). If the online-create line
   lands first and retires the Python literal, the test compares three copies
   instead of four.

## Out of scope, noted

- Frontend `authState` carry-forward (`auth.svelte.ts:155`): TS interfaces are
  runtime-erased and the frontend has no unit-test vertical by policy. Nearest
  guard: a backend assertion that `compute_user_full`'s exclusion set is
  exactly `{calendar_token}`, which pins the backend half of the pairing —
  include it in the access-levels test. The hazard entry itself stays.
- Projection backfill ("only affects rows written afterwards") stays — wiki
  already records that no test can catch it.
