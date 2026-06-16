# 215 — IC member delete (VEKN-less) + symmetric Mark-Deceased

## Why
Beta members list shows live `(unknown)` members — no name, no VEKN, just an
old-archon email (e.g. `neubauten2019@libero.it`).

Root cause: pre-#169 `merge_member` did `db.save_user(user)` **live** for every
new member regardless of `vekn_id`. #169 (`a048ee4`) added `seed_vekn_less_shell`
(soft-deleted shells) but it (a) only runs on the no-existing-row path and (b)
**never modifies an existing row** — so beta's pre-#169 live VEKN-less rows were
never demoted. They pass the `!deleted_at` list filter (`getFilteredUsers`,
db.ts) → visible. Discriminator for the residue: `vekn_synced=true AND no
vekn_id` (VEKN sync's `_create_user` always has a vekn_id; in-app signups are
`vekn_synced=false`).

Chosen over a one-time bulk SQL cleanup: a reusable IC tool.

## Design — per-member, symmetric
| Member       | Offered        | Refused      |
|--------------|----------------|--------------|
| Has VEKN ID  | Mark Deceased  | Delete       |
| VEKN-less    | Delete (soft)  | Mark Deceased|

- **Soft**-delete (set `deleted_at`), never hard: historical tournament
  player/seating refs must still resolve (`sync.ts` keeps deleted users cached;
  the list filter hides them). Mirrors what `seed_vekn_less_shell` produces.
- VEKN-less-only because deleting a VEKN-bearing member would resurrect on the
  next daily VEKN sync (`vekn_sync._get_user_by_vekn_id` filters
  `deleted_at IS NULL` → misses the tombstone → `_create_user` re-adds it).
- Permission: **IC only** (owner's call). Role-authz in the engine; the
  VEKN-less/VEKN-bearing *target* constraint is data-state validation in the
  route + UI (precedent: `merge_users` vekn-immovable check lives in accounts.py).

## Layers
1. **engine/src/permissions.rs** — `can_delete_member(actor) -> PermissionResult`
   = IC-only (role-only, no country; mirror `can_mark_deceased` shape). + unit test.
2. **engine/src/lib.rs** — `can_delete_member_json` + WASM `can_delete_member` +
   PyO3 `can_delete_member`. Rebuild PyO3 (maturin) + WASM (wasm-pack; prepend
   `~/.cargo/bin` for rustup's wasm32 toolchain).
3. **backend/src/permissions.py** — `can_delete_member(actor)` wrapper.
4. **backend/src/routes/users.py** —
   - `DELETE /api/users/{uid}`: gate `can_delete_member`; refuse self (403);
     404 if missing; refuse if `target.vekn_id` set (400, point to Mark
     Deceased); `soft_delete_user(uid)` + `broadcast_precomputed`.
   - `set_deceased`: refuse SETTING (`deceased=True`) when `target.vekn_id is
     None` (400, point to Delete). Allow clearing always (no trap for legacy
     mis-marks).
5. **frontend/src/lib/engine.ts** — `canDeleteMember(actor)`.
6. **frontend/src/lib/api.ts** — `deleteMember(uid)`.
7. **frontend/src/lib/components/VeknManagement.svelte** —
   - Delete button + confirm modal inside the `{#if !user.vekn_id}` branch
     (destructive style, mirror force-abandon). New `canDelete` prop.
   - Gate the Deceased block additionally on `user.vekn_id`.
8. **frontend/src/routes/users/[uid]/+page.svelte** — compute + pass `canDelete`.
9. **i18n** — 5 locales: delete button label, modal title, confirm body,
   warning, success toast. (Deceased strings already exist.)

## Out of scope / follow-up
- The existing live residue still needs to be cleared once the button ships
  (IC clicks through, or a one-off pass). The button is the mechanism; the
  cleanup is the act. Note in handoff.
- Optional self-healing ETL (demote live `vekn_synced`+no-vekn rows in
  `merge_member`) — not in this ticket; would need principal-engineer review of
  the just-reworked #169 merge.

## Client hard-deletes on tombstone (folded in)
Removed the `users` special-case in `sync.ts` that *stored* soft-deleted user
rows (justified by tournament `user_uid → name` resolution). It's unjustified:
every deletable member is VEKN-less and tournament participation requires a
`vekn_id`, so a deleted user is never a live player ref. Users now hard-delete on
a tombstone like every other type — the Universal Soft-Delete invariant
(SYNC.md), which the special-case had been deviating from. Server-side
`deleted_at` stays (retention window for streaming the deletion to catch-up
clients). `getAllUsers`/`getFilteredUsers` keep `!deleted_at` as a defensive
filter for pre-change rows until clients resync. Cosmetic cost: ~9 legacy
pre-VEKN tournament refs to nameless members now show a raw uid. SYNC.md
precised so the deviation isn't reintroduced.

## Load-bearing invariant
The daily legacy-archon merge does **not** resurrect a deleted member because
`soft_delete_user` keeps the row under its **same uid**, so
`seed_vekn_less_shell`'s by-uid guard finds the soft-deleted row and
early-returns. This safety relies on uid-preservation on delete — if a future
change ever re-keys the soft-delete, re-check the merge path.

## Acceptance
- IC sees Delete only on VEKN-less members, Mark Deceased only on VEKN-bearing.
- Delete soft-deletes (row stays for ref resolution; vanishes from list).
- Backend rejects: non-IC delete, self-delete, delete of a VEKN-bearing member,
  setting deceased on a VEKN-less member.
- Engine unit test green; PyO3 + WASM rebuilt; backend + frontend gates green.
