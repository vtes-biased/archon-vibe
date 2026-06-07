# #59 — VEKN account-surgery: the detach/merge invariant

Scope grew from "dedup the strip/split twins + fix merge_users field-listing" into
agreeing the **domain rule** the three functions must all obey. Recorded here so future
account-surgery changes start from the rule, not from re-deriving it. Discussed with PM;
reviewed by principal-engineer + senior-qa.

## The invariant (the durable rule)

> **A `uid` that carries a `vekn_id` is immovable.** It is never re-keyed and never
> soft-deleted. Everything linked to it stays linked to it. The person *without* the
> `vekn_id` is the only thing that ever moves.

Why this is the whole point: a VEKN ID is a permanent competitive/disciplinary identity.
All history objects (Sanction, DeckObject, tournament Player/Standing rows) key on `uid`,
never on `vekn_id`. So if the vekn-bearing uid stays stable, **all linked history stays
attached for free** — no reassignment, no per-field policy table. The only real work is
partitioning the *embedded* `User` struct fields between the record and the departing person.

### Corollaries
- **detach** (was strip + split → one `detach_user_from_vekn`): the original uid keeps the
  `vekn_id` + everything; the human gets a fresh uid with login (auth methods) + PII only.
- **merge** (`/claim`, `/link`, admin/discord merges): the survivor (`keep_uid`) MUST be the
  vekn-bearing uid; the dying `delete_uid` is the non-vekn one, and **all of its linked
  objects (auth, sanctions, decks) must migrate to the survivor** before soft-delete.

## Embedded User-field partition (the only per-field decision)

- **Follows the person** (nulled on the VEKN record, copied to the new account):
  name*, nickname, avatar_path, contact_email, contact_discord, discord_id, contact_phone,
  phone_is_whatsapp.  (*name kept on both — required field + registered name.)
- **Stays with the VEKN record** (default for anything not explicitly PII): vekn_id, roles,
  coopted_by/at, vekn_prefix, vekn_synced/at, ratings (constructed/limited × online/offline),
  wins, community_links (official), country/city/city_geoname_id/state (jurisdiction).
- **calendar_token follows the human** (NOT in the full projection, so it needs an explicit
  `get_calendar_token()` read). Both `merge_users` and `detach` carry it to the surviving
  personal account so the owner's existing `.ics` subscription URL keeps resolving. Detach
  clears it on the orphan first so the token is never duplicated. (Earlier, ticket #4 fixed
  `merge` to carry it but left strip/split dropping it — #59 makes the two consistent.)
- Default for a *new* field is "stays with the record" — competitive data must never leak to
  the detached person. When adding a User field, only add it to the PII list if it is truly
  personal/login.

## Bugs this fixes
1. `merge_users` built `User(...)` from scratch and omitted `resync_after` → silently reset
   every merge; any future field would meet the same fate. → build via
   `msgspec.structs.replace(keep_user, …)` so unlisted fields survive.
2. `merge_users` never reassigned **decks** → `/claim` orphaned the claimer's decks on their
   soon-soft-deleted uid. → add `reassign_decks`. (tracked as #65, fixed here)
3. `split` left `discord_id` on the orphaned VEKN record → stale PII re-broadcast (full
   projection) + re-pushed to VEKN (vekn_sync.py:838). `strip` nulled it. → unified detach nulls it.
4. `split` didn't bump `modified` on the orphan (strip did) → stale payload timestamp. → unified sets it.

## Decisions taken (and rejected alternatives)
- **Collapse strip + split into one `detach_user_from_vekn(uid) -> (personal, vekn_record)`.**
  Every divergence between them was a bug, not intent. The only genuine difference (displace is
  followed by a re-merge into the new owner) lives in the caller `/link`, not in the function.
- **Rejected the PM's level-aware exception** ("active suspension/probation follow the human").
  It would force detach to query+partition sanctions by level — exactly the acrobatic special-
  casing we set out to remove. Instead we keep the rule pure AND close the sanction-dodge with a
  single guard: **you cannot self-`/abandon` a VEKN ID while you hold an active
  suspension/probation** (`user_has_active_suspension`). Admin `/force-abandon` is exempt
  (officials act deliberately). Accepted residual edge: an official could still sponsor a fresh
  ID to a known-suspended person — a human-governance problem, not a data one, gated by
  no-VEKN-ID-means-cannot-compete.

## Known consequences / follow-ups
- **`/link` displace inherits the holder's history (incl. active sanctions) — ACCEPTED.**
  Under the pure rule, displacing a claimed VEKN ID and merging it into a new owner hands that
  owner the record's full history, including any active suspension. **Decision: leave as-is, no
  `/link` guard.** It's consistent with the invariant and admin-initiated — an organizer can
  lift the sanction if inappropriate. Only self-`/abandon` is guarded, because that's the one
  path where the *same* person tries to escape their *own* active sanction. We deliberately do
  NOT special-case the admin paths (keeps the rule pure; avoids the acrobatic branching #59 removed).
- **Live SSE propagation lag (#66).** detach/merge only `broadcast_resync(owner_uid)`; the
  orphan/merged record's `update_user` BroadcastData is discarded, so other connected clients
  keep stale cached copies (incl. the now-nulled orphan discord_id) until reconnect. DB +
  VEKN-push + fresh snapshots are correct. Pre-existing; tracked as #66.

## Out of scope / deferred
- Whether `merge_users` should migrate other uid-keyed references beyond auth/sanction/deck/
  coopted-by (none known today) — revisit if a new linked object type appears.
