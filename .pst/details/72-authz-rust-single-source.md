# EPIC #72 — Unify authorization in the Rust engine

**Supersedes #51.** #51 was scoped as "consolidate scattered backend permission checks into
one Python `permissions.py`." During the discuss-before-code step (owner + principal-engineer)
that target was rejected: a Python-only module **entrenches** the copy the frontend already
re-implements in TS, then gets undone. The correct single source is the Rust engine.

## The decision (durable rule)

> Authorization predicates (role / country / uid / ownership checks) live in
> `engine/src/permissions.rs` as the single source, exposed via **PyO3** (backend) and
> **WASM** (frontend). This is the agreed **cross-stack-DRY exception** to the owner's usual
> locality-over-DRY default — because the duplication is byte-identical AND security-sensitive
> (a silent divergence is privilege-escalation or wrongful denial).

Recorded as principal-engineer project memory `project_authz_single_source_rust.md`.

## Why this is right (grounded in code, 2026-06-08)

The pattern **already exists and is half-done**:
- `engine/src/permissions.rs` has `Role`, `UserContext{roles,country,vekn_id}`,
  `PermissionResult{allowed,reason}`, and `can_change_role` / `can_manage_vekn` /
  `can_edit_user`, exposed via PyO3 (`lib.rs` ~400) **and** WASM (`#[wasm_bindgen]` ~263).
- `ActorContext::can_manage_tournaments()` (tournament/types.rs:286) already IS the
  IC/NC/Prince "is_official" check.
- Backend `users.py:_can_change_role` already delegates to the engine — proof the path works.

But the rest is triplicated:
- **Python** re-implements `_can_manage_country` (vekn.py:36 == admin.py:29), the IC/NC/Prince
  gate inline ≥6× (vekn sponsor/link/force-abandon, admin merge, users.py:72, profile.py:151),
  `_is_organizer` (tournaments.py:66), `_can_manage_leagues`/`_can_edit_league` (leagues.py:48,53).
  Notably `can_manage_vekn` already exists in Rust and the backend does NOT call it.
- **TS** re-implements `is_organizer` + `can_organize_league_uids` natively in
  `engine.ts:450-463` (`isIC || organizers_uids.includes(uid) || (NC && country===country)`).

## Boundary (what moves, what stays)

**Into `permissions.rs` (pure fns of roles/country/uid + a flat target descriptor):**
`is_organizer`, `can_manage_country`, `can_manage_leagues`, `can_edit_league`,
`can_issue_sanction`, `can_lift_sanction`. Reuse existing `can_manage_vekn` and
`ActorContext::can_manage_tournaments`.

**Stays in Python:** all DB I/O. The two sanction checks fetch tournament/league today; keep
that async fetch in `sanctions.py` and pass already-fetched objects as **flat descriptors**
(`{organizers_uids, country, league_uid, league_organizers, level}`). Never serialize whole
domain objects across the PyO3/WASM JSON boundary.

## Guardrails (acceptance criteria for every child)

- Rust owns only the **decision** (`PermissionResult.allowed`). Each stack keeps its own
  message: backend per-call-site `HTTPException(403, "<distinct detail>")`, frontend uses
  `reason` for UX. Do **not** centralize HTTP error copy / i18n strings into Rust reasons
  (would couple the API contract + translations to WASM rebuilds).
- The **backend remains the authoritative enforcement point** — it still executes the check and
  raises 403. Moving the *logic* to Rust does not weaken server-side enforcement.
- The **frontend is UX-only and MUST fail closed**: a null/cold WASM engine returns
  `{allowed: false}`, never default-allow.
- **Perf:** PyO3 cost is negligible vs the DB round-trip. The only hot path is per-row UI gating
  (PlayersTab) — hoist the constant actor context out of the row loop (frontend already does).

## Children (ordered — engine first, it unblocks the rest)

- **#73 engine** — add the pure predicates + unit tests; mirror PyO3 + WASM bindings.
- **#74 backend** — wire routes to the engine; delete the Python `_can_*` copies; keep 403 detail.
- **#75 backend/sanctions** — sanction predicates in Rust with flat descriptors; DB fetch stays Python.
- **#76 frontend** — wire to the engine; drop the TS reimplementation; fail-closed on cold WASM.
