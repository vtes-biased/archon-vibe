Doc-impact: `wiki/hazards.md` ("Lazy imports hide references" deleted), `wiki/dev.md#lint-gates` (new gate listed, gate count updated).

# In-function imports

Owner rule: in-function imports are removed, not linted. The only exceptions are
listed ones for imports needed less than once a week that cost more than 5MB — the
PDF generator (`fpdf`, `backend/src/nda.py:157-158`) is the expected one; measure
it at ship time.

Inventory at intake (2026-09-27), `backend/src`:

- 63 relative `from .x import y` nested inside functions — `main.py` 28,
  `routes/tournaments.py` 17, `routes/sanctions.py` 3, `routes/calendar.py` 3,
  `archon_import.py` 3, `vekn_push.py` 2, `routes/users.py` 2, one each in
  `snapshots`, `routes/vekn`, `routes/admin`, `roles_hook/__init__`, `ratings`. All
  resolve today (static AST check). Many exist to break import cycles, which the
  removal has to resolve rather than move.
- Absolute nested imports: `github_app.py:42` `jwt`, `vekn_api.py:446-447`
  `asyncio`/`datetime`, `main.py:1099` `timedelta`, `main.py:1164` `time`,
  `roles_hook/__init__.py:169` `datetime`, `routes/users.py:143,300` `asyncio`,
  `routes/oauth.py:77` `base64`, and `nda.py:157-158` `fpdf`.

The gate follows the `scripts/check_*.py` pattern (see `fold-grammar`: it also
fails on a listed exception that no longer imports in-function), wired into both
`just lint` and `just lint-check`.
