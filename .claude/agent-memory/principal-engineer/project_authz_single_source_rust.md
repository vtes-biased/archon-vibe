---
name: authz-single-source-rust
description: Authorization predicates are the agreed cross-stack-DRY exception; single source is engine/src/permissions.rs (PyO3 backend + WASM frontend), not a Python module
metadata:
  type: project
---

Authorization predicates (role/country/uid checks: is_official, can_manage_vekn, is_organizer, can_edit_league, can_manage_leagues, can_issue/lift_sanction) belong in the Rust engine `engine/src/permissions.rs` as the single source, exposed via PyO3 (backend) and WASM (frontend). Originated from pst #51 (epic #47 code-quality), which was originally scoped as "consolidate into a Python permissions module" — re-scoped because Python-only leaves the frontend re-implementing the same checks in TS.

**Why:** The duplication is byte-identical AND security-sensitive (silent privilege-escalation / wrongful-denial on divergence). `can_change_role`/`can_manage_vekn`/`can_edit_user` already prove the Rust→PyO3+WASM pattern; `ActorContext::can_manage_tournaments()` already exists. The frontend genuinely needs the same predicates for UI gating, so only Rust removes both copies. This is the rare case where cross-stack DRY beats the owner's usual locality-over-DRY preference (feedback_locality_over_dry in the owner's repo memory) — locality is for cheap, low-stakes, greppable code; authz is neither.

**How to apply:**
- New authz predicate → add to permissions.rs (pure fn of roles/country/uid + a flat target descriptor), not inline in a route.
- Keep DB I/O in Python: pass already-fetched tournament/league as flat `{organizers_uids, country, league_uid}` descriptors; never serialize whole objects across the boundary.
- Rust owns the *decision* (`PermissionResult.allowed`); each stack owns its own message. Backend keeps per-call-site `HTTPException(403, detail)`; do NOT centralize HTTP error copy into Rust reasons (couples API contract + i18n to WASM rebuilds).
- Backend still executes the check and raises 403 — moving logic to Rust does NOT weaken server-side enforcement. Frontend copy is UX-only.
- Frontend wrappers MUST fail closed on a null/cold WASM engine (return `{allowed: false}`), never default-allow. Hoist constant actor context out of per-row UI loops to avoid per-row JSON↔WASM cost.
