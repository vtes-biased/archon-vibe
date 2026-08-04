# Permission model realignment (epic #538)

Audit date 2026-08-04. Target matrix from owner, same day.

## Target matrix

| Actor | Authority |
|---|---|
| IC | admin — anything, anywhere. Sole holder of: account merge (#536), member deletion, promo management, OAuth client management (#546), tournament force-unlock, global link promotion |
| NC | appoint/demote **Prince** in own country; edit own-country members' **profile data** (not their roles); create tournaments **and leagues**; moderate own-country community links incl. national promotion (#545); lift non-suspension sanctions in own country; record promo intakes; mark deceased (own country) |
| Prince | create members / sponsor VEKN ids; create tournaments. **Nothing else** — no member-data authority, no league creation, no link moderation, no full-data visibility |
| Rulemonger | appoint/demote Judge + Sheriff (stored value stays `Judgekin`, #547); lift non-suspension sanctions anywhere |
| PTC | appoint/demote PT |
| Ethics | issue + lift suspensions/probations; modify/delete any sanction |
| Judge / Sheriff / PT | badges only — no authority |
| DEV | OAuth client management (IC or DEV — unchanged, #546) |
| tournament organizer | own tournament: issue/delete organizer-level sanctions, run the event |
| league organizer | own league: edit it, lift a DQ in its tournaments |

Scope conventions: "own country" = actor's `country` equals target's; IC is never country-scoped.

## Where the code stands today

Already matching the target — no change needed:

- `can_change_role` (`engine/src/permissions.rs:121`) is exactly the appointment matrix: IC any; NC→Prince same country; PTC→PT; Rulemonger→Judge/Judgekin; target must hold a `vekn_id`.
- `can_mark_deceased` (`:274`) — IC + NC same country, Prince already excluded.
- `can_delete_member` (`:296`) — IC only.
- `can_issue_sanction` (`:410`) — suspension/probation restricted to IC + Ethics.
- `require_role` (`backend/src/middleware/auth.py:126`) grants IC implicitly, so "IC can do anything" holds for every route using it.

Diverging from the target:

1. `can_edit_user` (`:186`) grants Prince same-country profile edit → **#534**.
2. `can_manage_vekn` (`:163`) and `can_manage_country` (`:261`) grant Prince VEKN link / force-abandon / merge → **#534**.
3. `POST /admin/users/merge` (`backend/src/routes/admin.py:160`) is NC/Prince-reachable and unions roles without consulting `can_change_role` → **#536** (becomes IC-only).
4. Role changes are unreachable for a bare Rulemonger/PTC — `PUT /users/{uid}` gates on `can_edit_user` before the per-role check → **#535**.
5. `can_change_country` exists only in Python (`backend/src/permissions.py:60`), so the frontend cannot gate the country select → **#537**.
6. Community-link moderation (`backend/src/routes/users.py:478-500`) gives Prince hide/clear on same-country members → **#545**.
7. Prince holds the same-country FULL-data overlay (`db.py:256/304`, `broadcast.py:156`, `main.py:1032`) → **#544**.
8. The `Judgekin` label must read **Sheriff** in the UI, value unchanged → **#547**.

## The four-surface problem

The same rule is re-stated in up to four places, and they already disagree:

- **Engine** `engine/src/permissions.rs` — the sanctioned home (module docstring of `backend/src/permissions.py` says the logic lives there and the adapter "must NOT re-implement any rule").
- **Backend** — `can_change_country` is Python-only; plus inline `Role.X in user.roles` checks that never reach the engine: `admin.py:76/98/120/149`, `promos.py:65/194/199/247`, `sanctions.py:468` (modify = IC/Ethics), `tournaments.py:2939` (force-unlock = IC), `users.py:478-480` (link moderation), `oauth.py:580/628/648/680` (`require_role(Role.DEV)`).
- **Frontend** — role literals instead of engine calls: `hasAnyRole("IC","NC","Prince")` in `tournaments/+page.svelte:82`, `tournaments/new/+page.svelte:12`, `tournaments/[uid]/+page.svelte:127`, `CreateAndRegisterModal.svelte:39`, `UserList.svelte:53`, `users/[uid]/+page.svelte:89/95`, `CommunityTab.svelte:38`, `ProfileView.svelte:33`, `User.svelte:186`; `hasAnyRole("IC","NC")` in `leagues/+page.svelte:23`, `leagues/new/+page.svelte:13`.
- **Bot** — `bot/src/archon_bot/config.py:28` `SETUP_ROLES={IC,NC,Prince}`, `:30` `SANCTION_ROLES={IC,NC,Prince,Ethics}`. The sanction set does not match `can_issue_sanction` (IC/Ethics/organizer), so the bot offers `/sanction` to NC/Prince of any country and the backend then refuses. Client affordance only — sanction routes do go through the engine (`sanctions.py:57-92`) — but it is a fourth copy of the matrix.

`is_official()` (`backend/src/permissions.py:29`) is a further conflation: it answers "may create/manage tournaments" (`can_manage_tournaments`, IC/NC/Prince) but is used as the gate for **member creation** (`users.py:78`) and **sponsoring** (`vekn.py:206`). Those coincide today and still coincide under the target matrix, but they are two different questions sharing one function — separate them so a future divergence is expressible.

## Design objective

One declarative table in the engine that a matrix change edits in **one** place, exposed via PyO3 + WASM, with backend routes and frontend gates as thin callers and no role literal outside the engine. Concretely:

- Name every distinct authority as a capability (edit_member_profile, change_role, manage_vekn, merge_accounts, create_member, sponsor_vekn, create_tournament, create_league, moderate_link, issue_sanction, lift_sanction, force_unlock, manage_promos, manage_oauth_clients, …).
- Express each capability as data: allowed roles + a scope predicate (global / same-country / owns-resource / self) + any target-state precondition. Deny by default.
- Keep the returned `PermissionResult { allowed, reason }` shape — the reason strings are already user-facing.
- The frontend gets one wrapper per capability; `hasAnyRole` survives only for cosmetic role display (badges, sort order), never for gating.
- The bot asks the backend rather than carrying its own role sets (an existing `/me`-style capability payload, or gate on the API's 403).
- A CI check (**#548**) fails the build on any role literal used for gating outside the engine, with a small commented allowlist for the cosmetic and projection uses — otherwise the drift returns one component at a time.

Deliberately out of scope: **access levels**. `access_levels.py` / `broadcast.py` / `db.py` compute *visibility* projections from the same roles, which is a separate axis (see SYNC.md) — only OPEN DECISION 2 touches it, and only to confirm Prince's overlay stays as-is.

## DECISIONS (owner, 2026-08-04 — all resolved, no blockers left)

1. **Princes do not create leagues.** Keep `can_manage_leagues` at IC/NC. `open_to_country_princes` (`can_link_tournament_to_league:358`) stays the Prince path — attach-only, no league edit rights.
2. **Prince loses same-country full-data visibility** → **#544**. Viewer-side only; the subject-side projections that publish an official's own contact info (`access_levels.py:102/122`, the Officials Directory from #108-#110) are untouched.
3. **Link moderation drops Prince**, NC same-country only → **#545**.
4. **Sanction lifting stays as-is**: Rulemonger anywhere, NC in the tournament's country, IC/Ethics for suspension+probation, league organizer for a DQ. Recorded in the matrix above; no code change.
5. **Promo chain unchanged**, now recorded in the matrix: IC manages, NC records intakes + sees the whole ledger + gets full promo access regardless of country.
6. **OAuth client management stays IC or DEV** — unchanged, #546 closed with no code change. The capability table must preserve the DEV grant.
7. **Rulemonger appointing Judgekin is intended**; the label becomes **Sheriff** (display only, stored value stays `Judgekin`) → **#547**.
