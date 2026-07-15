---
name: project-permission-marshalling-gap
description: Engine permission unit tests bypass OwnedResource::from_json (struct literals), so a new descriptor JSON key has zero coverage — pin it with a backend permissions.py wrapper test.
metadata:
  type: project
---

Engine permission tests in `engine/src/permissions.rs` build `OwnedResource`
(and similar contexts) via **struct literals** (`OwnedResource { country, organizers_uids, .. }`),
never through `from_json`. So when a permission gains a **new descriptor field**
that crosses the PyO3/WASM JSON boundary (e.g. `open_to_country_princes` for
`can_link_tournament_to_league`), the engine test covers the *logic* but NOT the
*marshalling*: the `value["new_key"].as_bool()` parse in `from_json` and the
backend's descriptor-build in `permissions.py` have **zero incidental coverage**.

**Why it matters:** the backend `can_link_tournament_to_league` builds a BESPOKE
descriptor dict inline (it does NOT reuse the shared `_resource()` helper, which
omits the flag). A future DRY consolidation onto `_resource`, or a key-string
typo on either side, silently drops the flag → the grant fails **closed** (e.g.
same-country Prince denied attach) with no error and no failing test.

**How to apply:** for a new permission field that only matters on one grant
branch, add ONE backend test at the `permissions.<fn>(user, obj)` interface
(real msgspec model → real PyO3 engine, no DB, no mocks) asserting only the
flag-sensitive outcomes (with-flag → allow, default → deny). This exercises both
sides of the marshalling contract at once. Do NOT re-test the full logic matrix —
that's the engine test's job. Pattern + home: `test_organizer_access.py`
(`TestCanLinkTournamentToLeague`). Related: [[project_engine_model_state_drift]].
