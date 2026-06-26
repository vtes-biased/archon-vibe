---
name: trap-flaky-update-user-mock-officials
description: RESOLVED — test_users.py::test_update_user flakily 403d because unseeded mock data fabricated engine-impossible officials (roles but no vekn_id); fixed in generate_mock_users. Worked example of the engine-impossible-fixture class.
metadata:
  type: project
---

**RESOLVED 2026-06** in `generate_mock_users` (roles are now decided first and
any user with roles is forced a vekn_id). Kept as a worked example of the
"never encode engine-impossible states" fixture class. Original diagnosis below.

`backend/tests/test_users.py::test_update_user` used to fail intermittently
(~5-12% of runs) with `assert 403 == 200` — an IC admin denied editing a user's country.
**It is NOT a regression and NOT OAuth-related.** Reproduces in `test_users.py`
alone and in a pure `permissions` script with zero OAuth code.

**Root cause:** `tests/mock_vekn_data.py::generate_mock_users` calls `random.*`
with **no seed** and assigns roles independently of `vekn_id` — so ~20% of the
time it fabricates an *official* (IC/NC/Prince role) with `vekn_id=None`, a state
production forbids (roles require a vekn_id). The test picks `admin = first IC`
and `target = first other user`; when that target is a vekn-less official and the
PUT changes country, `permissions.can_change_country` → `can_change_role`, and the
engine's `can_change_role` (`engine/src/permissions.rs`) denies on
`target.vekn_id.is_none()` **before** the `actor.has_role(IC)` bypass → 403.
`can_change_country`'s own docstring even asserts "an official always has a
vekn_id" — true in prod, false in this mock data.

**Why:** classic "never encode engine-impossible states" violation (see CLAUDE.md
working conventions + [[project_engine_test_fixture_traps]]).
**How to apply:** when you see this flaky 403, don't hunt for a regression — it's
the mock generator. The source fix: in `generate_mock_users`, force a `vekn_id`
whenever `user_roles` is non-empty (mirror the prod invariant) and/or seed the
RNG. Ticket-worthy (flaky red); the engine ordering itself is harmless in prod.
