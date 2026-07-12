---
name: bot-test-topology
description: How bot/ tests are structured — why validated fakes are legit here (no real backend/Discord), the guard-test pattern, and the one real-artifact seam (token_store).
metadata:
  type: project
---

The Discord bot (`bot/`, pure OAuth client to the backend) has **no real backend
and no Discord integration test** available in-suite — so the "never mock the DB
/engine, real-run only" rule from [[engine-test-topology]] and CLAUDE.md does NOT
transfer here. Validated fakes are the accepted, correct pattern for bot tests.

**Why:** you cannot hit real Discord REST or a real Archon backend from the bot
test venv. Rejecting a fake-based bot test reflexively (as you would a backend
mock) is the wrong call.

**How to apply / what "validated fake" means (the bar bot tests must still clear):**
- Fakes must model the REAL contract, and the strong ones ship a **guard test**
  proving the fake reproduces the real behavior — e.g. `test_refresh_single_flight.py::test_fake_backend_models_the_bug`
  drives the fake into the backend's reuse-detection chain-revocation to prove the
  regression tests above it are meaningful. A fake without that guard is weaker.
- Assert at the **observable-effect interface**: for reconcile, the set of REST
  overwrite edits/removes (`edited_overwrites`/`removed_overwrites`), not internals.
  `test_reconcile_channels.py` even makes the fake's `fetch_channel` RAISE to pin
  the principal-engineer "no per-channel fetch" hard requirement.
- Prefer the **shipped pure function**: `sanction_table_channel` (routing) is
  extracted pure and tested with zero fakes — the gold standard when available.
- `token_store.py` is the ONE bot component testable against a **real artifact**
  (real aiosqlite DB, no mock). If a token_store regression is worth pinning, do
  it against a real temp/in-memory DB.

**Frame-parsing drift hazard:** `_read_probe_frames` (probe_tournament) duplicates
the SSE loop's `data:`-line accumulation + `sync_complete` boundary logic ("parsing
mirrors the SSE loop"). It shares `_normalize_events` but not the accumulation —
testing the probe parser would test a copy. If these diverge it's a real bug; the
fix is sharing the accumulator, not adding a copy-asserting test.

**start_sse is idempotent** (`if key in _sse_tasks and not done(): return`) — the
oauth-callback respawn loop leans on this to no-op live listeners. It's a 2-line
inspectable guard; not worth a create_task-call-count test.
