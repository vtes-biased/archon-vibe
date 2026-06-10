---
name: rounds-standings-coupling-engine
description: Rust engine invariant — a tournament's standings are non-empty iff rounds are non-empty; makes the VEKN batch_push rounds-guard safe
metadata:
  type: project
---

In the Rust engine, an in-app tournament has non-empty `standings` **if and only if** it has non-empty `rounds`.

**Why:** `update_standings` (`engine/src/tournament/standings.rs:114`) early-returns when `rounds` is empty — it never synthesizes standings from scratch. `SetScore` (`engine/src/tournament/mod.rs:1239`) requires an existing round/table. `FinishTournament` allows `Waiting`→`Finished` (no rounds played) but then standings stay empty too. Only the VEKN importer (`vekn_tournament_sync.py`) writes standings with empty rounds (`models.py:549` "no rounds data in that case").

**How to apply:** Any backend query/guard that wants "tournaments with real in-app play data" can key on `jsonb_array_length(rounds) > 0` and trust it excludes VEKN/ETL imports without dropping legitimate in-app tournaments. This is exactly what the VEKN `batch_push` step-3 results-push guard relies on (`vekn_push.py`, #124) — it prevents re-uploading imported results whose standings fold finals in (`generate_archondata` assumes prelim-only). Offline tournaments are overwritten with full state incl. rounds on go-online, so they pass. Don't "fix" a finished-but-empty-rounds tournament to push — there's nothing useful to send (`generate_archondata` would emit only "0¤"). See [[standings-prelim-only-contract]].
