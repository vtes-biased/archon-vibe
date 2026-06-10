# Deceased-member status

A respectful "in memoriam" status for members who have passed away. Adjacent to a
suspension but **not disciplinary** — deliberately kept out of the `Sanction` model.

## Why not a sanction
`Sanction` is disciplinary by construction (`level`, `category`, `issued_by`,
`expires_at` — `models.py:337`). Death isn't a disciplinary act; a deceased member must
not surface in "members with sanctions" views or interact with suspension logic.

## Data model (`User`, `models.py:275`)
- `deceased_at: datetime | None` — presence IS the flag, and records when. Follows the
  codebase's nullable-timestamp-as-flag idiom (`deleted_at`, `lifted_at`, `expires_at`).
- `deceased_by_uid: str | None` — audit trail, mirrors `lifted_by_uid` / `issued_by_uid`.
- Clearing = null both fields → naturally reversible (wrong-person mistakes happen).
- **Not** a soft-delete (`deleted_at`): the point is to PRESERVE history and ratings, not
  hide them. They stay ranked on leaderboards (explicit decision — not excluded).
- Add `deceased_at`/`deceased_by_uid` to `local_modifications` on write so the daily VEKN
  pull doesn't clobber them (`models.py:307` pattern). **Never push to VEKN** (no field
  for it there; stays archon-local).

## Permission (`engine/src/permissions.rs`)
- New `can_mark_deceased` engine fn, reusing the country-scope check used by
  `can_change_role` (engine ~`:143`): **IC unrestricted + same-country NC only**.
- **Prince excluded** — consistent with "only NC (not Prince) gets implicit organizer
  rights" (user memory). Set and clear share the same permission.
- Backend marshalling adapter in `backend/src/permissions.py`; route in
  `backend/src/routes/users.py` (pattern of `_can_change_role`).

## Visibility (`access_levels.py`)
- Project `deceased_at` at **member** access level (logged-in members see it).
- UI: small, subtle marker on the profile (icon, no banner) — "opt-in subtle" so it
  explains inactivity without an outsized memorial that families may not want.
- Localize the marker string in all 5 locales (i18n-translator).

## Behavior
- Pure status label everywhere EXCEPT tournament registration.
- Registration: organizer registering a deceased member → **warn/block** (engine check).
  Self-registration is moot (they won't log in).
- NOT excluded from active leaderboards / rating counts (explicit decision).

## Decisions captured (from design chat)
- Visibility: member-level, opt-in subtle.
- Behavior: pure label + warn/block new registration (no leaderboard exclusion).
- Who can set/clear: IC + same-country NC (no Prince).

## Implementation surface (Rust → backend → frontend → i18n → docs)
1. `engine`: add `deceased_at`/`deceased_by_uid` to the User shape if the engine carries
   it; add `can_mark_deceased`; registration guard. Rebuild WASM + PyO3.
2. `backend`: `models.py` fields; `access_levels.py` member projection; route + permission
   adapter; `local_modifications` handling; ensure vekn_push skips these fields.
3. `frontend`: subtle profile marker; mark/clear control gated to IC + same-country NC;
   registration warn/block surfacing.
4. i18n: marker + control + warning strings, 5 locales.
5. docs: note the new synced User field if SYNC.md enumerates them.

## Outcome (implemented)
- Engine: `can_mark_deceased` (IC + same-country NC, Prince excluded) + unit test;
  WASM `canMarkDeceased` + PyO3 binding.
- Backend: `User.deceased_at` / `deceased_by_uid`; `deceased_at` → member projection,
  `deceased_by_uid` → full only; `PATCH /api/users/{uid}/deceased` (self-marking blocked);
  `deceased_at` flagged in `local_modifications` (intentionally append-only — archon-local
  always wins over VEKN; never pushed). New projection-privacy test in test_access_levels.
- Frontend: `MemberStatus.svelte` control on the user detail page (gated by canMarkDeceased
  + online + not-self), subtle Flower2 in-memoriam marker on the profile, and a warn-with-
  confirm in AddPlayerForm. Registration guard is **frontend-only** (not an engine hard-error
  like DQ/suspension) — backfilling a finished event can legitimately add a since-deceased
  member; principal-engineer confirmed this placement is correct.
- i18n: 13 keys across all 5 locales ("In memoriam" kept as the Latin phrase everywhere).
- docs: SYNC.md projection table + ARCHITECTURE.md (User Account Surgery + authz wrappers).
- Drive-by (unrelated, was red on main): fixed stale `promote_international` →
  `promote_global` cases in test_community_link_moderation.py left over from refactor 97dee76.
- Verified green: cargo permissions tests (15), full backend suite (205), svelte-check (0).

## UX revision (post-review)
- Detail page: dropped the standalone MemberStatus section AND the name-header badge.
  The mark/clear control now lives inside the VEKN section (VeknManagement.svelte),
  gated by a `canMarkDeceased` prop — mention ("Recorded as deceased") shown only when
  deceased, no "not deceased" text. MemberStatus.svelte deleted; keys `deceased_title`
  and `deceased_status_none` removed from all 5 locales.
- New `DeceasedIcon.svelte` atom renders a subtle Flower2 before the name; added to the
  member-directory lists: members list (UserList), rankings, hall of fame. Scoped to
  those directories — tournament rosters resolve names via display_name/lookup (no
  deceased_at on the player object) and were left out as lower-value/higher-cost.
