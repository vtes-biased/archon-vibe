Doc-impact: `wiki/dev.md` — the credentials, and the standing decision that a dev
login is never an app feature (no frontend affordance, no backend endpoint), so a
convenience button is not re-proposed later. `wiki/testing.md` — one sentence
drawing the boundary against the e2e seed.

## What already exists

`backend/scripts/seed_e2e.py` mints `e2e-organizer@example.com` /
`E2eT3stP@ss!`, roles `[IC, ETHICS]`, VEKN id `9999901`, plus ten players with
Prince/NC roles. It is **not** reusable here: it opens with `DELETE FROM objects`
and `DELETE FROM auth_methods`, and refuses a non-empty target unless
`E2E_FORCE=1`. `just test-e2e` runs it inside its own compose project so teardown
can never reach the dev volume.

The dev database measured on 2026-09-02: **30016 objects, 1 auth method** (the
owner's own login). So the seed correctly refuses, and there is no second way in.
`just dev-reset` is `docker compose down -v` — it drops the dump, it does not help.

## Constraints that came from the owner

A fixed account with constant, documented credentials — not minted-and-printed.
An external script is fine; an app feature is not. Rejected alternative: attaching
a password to an existing member from the dump, which mutates real data and makes
the account's roles depend on whatever the dump happens to contain.

## Safety facts

`VEKN_SYNC_ENABLED` and `VEKN_PUSH` both default to false (`backend/src/main.py`)
and `just dev` sets neither, so a locally created member is never pushed upstream.
Keep the VEKN id outside `seed_e2e.py cleanup()`'s `9999%` / `9990%` predicate —
that cleanup has no non-empty guard and would otherwise delete this account.

A checked-in password is acceptable only because the script refuses any database
but the local dev one; that refusal is load-bearing, not decoration.
