---
name: online-create-bypasses-engine-gate
description: The online POST /tournaments route builds the Tournament struct directly in Python and does NOT call the engine create_tournament — so engine create-time gates are unenforced on the online create path
metadata:
  type: project
---

The engine's `create_tournament` (`engine/src/tournament/mod.rs`) runs create-time
validation (`validate_config_fields`, `validate_rank_legality`, …). But the **online**
create path does NOT go through it: `backend/src/routes/tournaments.py` `create_tournament`
(~811-903) constructs `Tournament(...)` directly in Python and calls `save_tournament` — no
PyO3 engine call. So any gate added to the Rust `create_tournament` is enforced only on:
- **Offline create** (`createTournamentOffline` → `createTournamentWithEngine` → WASM `engine.createTournament`) — gated.
- **UpdateConfig** (both online action route → PyO3 `apply_event`, and offline WASM) — gated.

**The online create path relies entirely on the frontend form** for create-time legality;
the server has no backstop. `_gate_offline_created_insert` (~2117, used by go_online /
sync_offline) also trusts the client payload ("the WASM engine enforced them client-side")
and does not re-run engine create gates. VEKN import (`vekn_tournament_sync.py`) and archon
migration (`migrate_from_archon.py`) likewise build `Tournament(...)` directly — engine-gate-free
(authoritative external data, but migration can carry legacy-illegal combos into the store).

**Why:** caught reviewing the #427 VEKN config-legality gate. The ticket said "in the engine
so create/config-edit/offline all share the gate", but online create silently doesn't share
it — the Python create route is a parallel, hand-rolled construction that predates the engine
entrypoint. Non-obvious because UpdateConfig *does* route through the engine, so you assume
create does too.

**How to apply:** any review of a ticket that says "enforce X at create time in the engine"
must check `backend/src/routes/tournaments.py`'s create route separately — the engine gate
does NOT cover it. A create-time invariant needs either a server-side check in that route
(ideally via a PyO3 call to keep the rule single-sourced in Rust) or acceptance that online
create is frontend-trust-only. Pairs with [[config-field-create-updateconfig-asymmetry]]
(the intra-engine two-site gap) — this is the higher-level Python-bypasses-engine gap.
