# Legacy-archon merge: VEKN-ID member matching + sync-first prod (#169)

Principal-engineer-reviewed 2026-06-14. Two coupled changes; both validated
("holds up with changes"). This file is the implementation spec; the migration
narrative lives in `.pst/details/35-*.md` (sync-first) and `115-*.md` (the merge).

## The bug (data loss)

`merge_member` (`backend/scripts/migrate_from_archon.py:429`) matches a legacy
member by **old-archon uid** (`get_user_by_uid(user.uid)`). When the live
new-stack account for that member carries a *different* uid — because a user
**claimed** a VEKN-sync-created identity copy (`/claim` keeps the vekn-sync
uuid7 as survivor: `routes/vekn.py:99` → `accounts.py` `merge_users:182`) — the
lookup misses (`existing is None`) and the "vekn-first echo" branch (`:435-453`)
**tombstones the live claimed account and nulls its `vekn_id`**. The user loses
their claimed identity, `auth_methods`, `community_links`, and local edits; a
fresh auth-less old-archon record takes the number. Community-links-vanishing is
the *same* incident — the field-merge loop (`:465-481`) never touches
`community_links`; they die with the tombstoned account.

This directly violates the `merge_users` invariant: "a uid carrying a `vekn_id`
is immovable and is NEVER soft-deleted" (`accounts.py:156-168`).

Surfaced on the #91 beta (sync-first ordering): owner claimed his VEKN id, the
merge detached him + wiped his community links. The runbook's leg-A stayed green
because *its* holders are all unclaimed identity copies, where tombstoning is
correct.

## Fix — match on `vekn_id`, never tombstone

Replace the uid-match + tombstone with VEKN-ID matching. `vekn_id` is the stable
cross-system identity key; 0 source-dup vekn_ids in the prod dump, so the match
is a clean bijection.

Per legacy member:
1. **No `vekn_id`** → **seed as a soft-deleted headless shell** under the old uid
   (mirror `member_deletions`, `:542-547`). Record `member_uid_map[old]=old`.
   Do **NOT** bare-drop (see "Why not drop" below).
2. **Match by `vekn_id`** (`live_user_by_vekn_id`):
   - **Found** → merge archon-owned `ARCHON_USER_FIELDS` into the live account,
     respecting `local_modifications`; never tombstone, never touch
     identity/`vekn_id`. `member_uid_map[old]=live.uid`.
   - **Not found** (vekn knows the member, the VEKN sync hasn't created the
     account yet — e.g. a member vekn.net dropped but archon still has) →
     seed-insert under the old uid. `member_uid_map[old]=old`.
3. **Remap every member-uid reference through `member_uid_map`** (next section).

In ETL/`--truncate` mode `member_uid_map` is the identity map (uids preserved),
so the remap is a no-op there — **one code path, both modes**.

## Why not drop vekn-less members (PE measured the dump)

The original premise — "the engine requires a `vekn_id` for any participant, so
vekn-less members hold no refs" — confuses the *new* engine gate
(`VeknIdRequired`, which gates only the in-app path) with *historical* imported
data. Old archon's `Register` event stored players unconditionally with
`vekn=""`; imported history never passed the new gate. Measured: **142 vekn-less
members; 9 tournament refs to them — 4 in `players`, 5 in round `seating[]` —
across 3 rich Finished events**: Granada Nocturna (v12784), Neonate Revolution
(v13209), Granada funeral-wake (no vekn id). A bare drop orphans those 9 seats in
the most-visible kind of event. Shell-seeding keeps the #38 "0 orphans" property.
These 3 events are the regression fixture.

## Complete member-uid reference enumeration (remap ALL of these)

The drafted list (players/winner/finalists/seating, `deck.user_uid`,
`sanction.user_uid`, `coopted_by`) was **incomplete**. Full set:

- `Tournament` rounds: `seating[].player_uid` **and** `seating[].judge_uid`
  (`Seat.judge_uid`, FK→users, `models.py:505`)
- `Tournament` finals: `seating[].player_uid`/`judge_uid` + **`FinalsTable.seed_order[]`**
  (a `list[str]` of user_uids, `models.py:527` — trivially missed in a per-player remap)
- `Tournament.standings[].user_uid` (`Standing.user_uid`)
- `Tournament.winner` / finalists
- `Tournament.organizers_uids[]`, `Tournament.offline_user_uid`
- `League.organizers_uids[]`
- `DeckObject.user_uid`
- `Sanction.user_uid` **and `Sanction.issued_by_uid`** (`build_sanction:622`, from
  `judge.uid`; 24 distinct issuers in prod)
- `User.coopted_by`

**Apply the remap to the rich payload WITHIN the step-2 merge-into-vekn-copy**
(`:1003-1037`), not only to standalone inserts — this is the load-bearing case
under sync-first (below).

## Sync-first coupling (Decision 2)

Prod goes **sync-first** (see `35-*.md`). This makes the remap mandatory, not
optional: the VEKN tournament sync writes player uids as the live account uid =
**uuid7** under sync-first (`vekn_tournament_sync.py:180/200/210`). When `--merge`
brings rich `rounds`/`seating`/`finals`/`decks` (old-archon uids) INTO a
vekn-created copy whose `players`/`standings` already key on uuid7, an un-remapped
merge **splits one tournament across two uid spaces** — which the cross-object
orphan scan won't catch (the old uid may still exist as a live account elsewhere).
Mitigation: the remap above + an **internal same-tournament uid-consistency
check** in the validator (every uid in rounds/seating/finals/standings/decks must
also appear in `players`).

Push-inertness (#114) under sync-first: **confirmed OK** — `_create_user` sets
`vekn_synced=True` (`vekn_sync.py:652`), so vekn-sync-created members owe no push;
`vekn_pushed_at` stamping survives the step-2 `msgspec.structs.replace` (in the
replace list). Still: re-run the #91 §7 audit on a **sync-first** seed (the prior
audit ran on the ETL seed — different member create path).

`coopted_by` convergence: VEKN sync infers `coopted_by=sponsor.uid` (uuid7); the
merge writes the remapped old sponsor. They agree by construction *when the
sponsor has a map entry* — the shell-seed (step 1) guarantees even vekn-less
sponsors get one, closing a daily flip-flop / orphan risk.

## Validator rework (same PR — it red-flags a CORRECT run otherwise)

`backend/scripts/migrate_validate.py`:
- `live users == members` (`:73`) → `live users == distinct vekn_ids (+ shells)`
  (18,861 + shells, not 19,003). Hard-fails on a correct sync-first run as written.
- tournament count (`:87`) + spot-check (`:249-264`) look up old tournaments by
  identical uid → broken for every event merged into a vekn copy (different
  surviving uid). Resolve via `external_ids.archon`/`.vekn`.
- add orphan scans for `seed_order`, `issued_by_uid`, `seating[].judge_uid`.
- add the internal same-tournament uid-consistency check.

## Secondary / nice-to-have

- **Tombstone-spanning unique index asymmetry** (`schema.sql:143` has no
  `deleted_at` exclusion; `get_user_by_vekn_id` `db.py:560` doesn't filter
  deleted, vs the merge's `live_user_by_vekn_id` which does). Ensure no residual
  seed-insert path can collide with a soft-deleted row holding the same vekn_id.
- **User-page deep links** by old-archon uid break under sync-first (uuid7 ≠ old
  uid). Covered by `old.archon.vekn.net` read-only for 30d — note in #40.
- Harmless consistency nit: `routes/auth/profile.py` never adds `community_links`
  to `local_modifications`, and `ARCHON_USER_FIELDS` omits it. No effect today
  (the field-loop ignores it); add both if `community_links` ever joins a sync's
  field set.

## Acceptance

- `migrate_validate` (reworked): 0 orphans, count parity on the new basis.
- The 3 vekn-less-ref tournaments intact (regression fixture).
- A claimed account survives a merge with `vekn_id` + `community_links` +
  `auth_methods` preserved.
- #91 leg-A (vekn-first/sync-first) + leg-B (DR `--truncate`) clean; §7 push audit
  all-zero on a **sync-first** seed.
- Daily re-run idempotent (no churn, no coopted_by flip-flop).

## Implementation (landed 2026-06-14)

`merge_member` (vekn-id match, no tombstone, `seed_vekn_less_shell`),
`migrate_members` (+`member_uid_map`/`coopted_pending`), `remap_coopted_by`,
`_remap_member_refs`, `save_sanctions`/`migrate_leagues` remaps, and the
`migrate_validate.py` orphan + internal-consistency scans. Tests:
`test_claimed_account_not_detached_by_merge`, `test_member_refs_remapped_and_vekn_less_seeded`.

**Principal-engineer-reviewed; 3 idempotence bugs found and fixed:**
1. `coopted_by` daily flip-flop — the merge loop wrote the old uid while
   `remap_coopted_by` wrote the live uid (70 members churned 2 writes/night).
   Fixed: the merge loop SKIPS `coopted_by`; `remap_coopted_by` is its sole,
   idempotent writer.
2. Validator finals scan had a masking AND-clause (player orphan hidden when the
   judge resolved) — split into clean player/judge scans.
3. Internal-consistency scan only covered rounds seating — extended to finals
   seating, `seed_order`, and standings (the full play-data uid surface).

**Validated at scale against the real prod dump (19,003 members / 8,371 tournaments):**
- ETL `--truncate`: output matches the prior rehearsal; `migrate_validate` 0
  orphans across all scans (incl. the new ones).
- Sync-first sim (seed 18,861 uuid7 accounts as if the VEKN sync ran first, then
  `--merge`): 142 vekn-less shells, **0 members inserted** (all matched by vekn
  id), **no tombstone**, all 18,861 accounts live; orphan scan 0 for every ref
  type incl. `rounds.seating.player_uid` / `finals.seed_order` /
  `sanction.issued_by_uid` and the internal split check; the 2 vekn-less-ref
  tournaments resolve their seats to shells. Player uids are uuid7 (remap proven).
- Idempotence: 3rd merge `members.unchanged 18861`, **0** coopted churn.

**Known benign wart (pre-existing, NOT #169):** ~6–12 tournaments get a harmless
`modified`-timestamp bump on each daily re-run — a `same_but_modified` Python-vs-
decoded comparison false-negative (verified: stored JSON is byte-identical except
`modified`; the member remap is fully idempotent). Could be tightened separately
by comparing serialized forms; out of scope for the detach fix.

## Ticket fan-out

- #35 / #115 — narratives updated (sync-first; vekn-matching). Done.
- #39 — add the cutover gate: refuse `--merge` if live vekn-account count < ~18k.
- #40 — no ordering change; add the user-deep-link note.
- #91 — add a sub-task: re-run the §7 push audit on a sync-first seed.
- #116 — unaffected (PG cluster sequencing is uid-agnostic).
