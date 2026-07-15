---
name: lazy-import-rename-trap
description: Renaming/moving a symbol can silently break function-level (lazy) import callers that neither module-load nor the test suite catch, especially inside try/except post-effect blocks.
metadata:
  type: feedback
---

When renaming or moving a Python symbol, grep for EVERY reference including function-level (lazy) imports — not just top-of-file imports and obvious call sites.

**Why:** This codebase uses lazy `from .x import y` inside function bodies heavily to break the `routes.tournaments` ⇄ `vekn_push` ⇄ `archon_import` import cycles. A lazy import is invisible at module load AND to a green test suite (the enclosing function isn't exercised), so a rename that misses it produces a runtime `ImportError`. Worse, several of these lazy imports sit inside `try/except Exception: logger.exception(...)` post-effect blocks (e.g. `apply_archon_import`'s TWDA+VEKN push, ratings recompute) — the ImportError is swallowed and silently disables the WHOLE block, including sibling symbols that were renamed correctly (a single failed `from ... import a, b` statement drops both `a` and `b`). Observed 2026-07: the `_maybe_submit_twda`→`maybe_submit_twda` rename missed `archon_import.py`'s lazy import, silently killing both the TWDA submit and `_maybe_push_vekn` on the import path while 279 backend tests stayed green.

**How to apply:** On any symbol rename/move, run `grep -rn "<old_name>" backend/` and check the hits that are inside function bodies (lazy imports) and docstrings, not only `import`-line hits. Assume the test suite will NOT catch a missed lazy-import caller.
