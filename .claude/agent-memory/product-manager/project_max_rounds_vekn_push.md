---
name: max-rounds-vekn-push
description: max_rounds is ONE per-player-cap concept; it IS pushed to VEKN (VEKN build requires it); only self_organized_rounds is the never-pushed non-VEKN mechanic
metadata:
  type: project
---

Authoritative ruling on `max_rounds` vs VEKN push (settled 2026-06-23; resolves a doc/code contradiction).

`max_rounds` is a SINGLE engine concept: a per-player round cap. `0` = uncapped/standard; `>0` = each player plays at most N rounds from a shared pool, retiring to `Completed` at cap. There is no second "open rounds" feature — the two frontend builds just relabel the same field (house build: "Open Rounds" checkbox + cap select; VEKN build: required "Max Rounds" 2/3/4, defaulting 3). Engine semantics in `engine/src/tournament/mod.rs:697-713`.

`max_rounds > 0` is NOT a non-VEKN marker and is NOT mutually exclusive with VEKN push — the prod/VEKN build (`VITE_VEKN_PUSH=true`) FORCES `max_rounds > 0` on every tournament. `vekn_push.py` (push_tournament_event line 147-150; UNCREATED_EVENTS_QUERY line 346) deliberately pushes these and is correct as-is. NOT a backend bug.

The genuinely non-VEKN, never-pushed mechanic is `self_organized_rounds` (trust-based, collusion-accepted house play; only settable on the house build). It's kept off VEKN today by deployment separation (house build has no vekn_push_client), NOT by a query guard — a latent invariant if instances ever converge.

**Why:** TOURNAMENTS.md historically labeled "Open Rounds (per-player cap)" as "Non-VEKN format / Not pushed to VEKN" — that blanket claim is false and contradicted the (correct) code.

**How to apply:**
- Disabled max_rounds/open_rounds toggle = "round count locked after start OR VEKN registration" (frozen-after-commit), NOT "VEKN tournaments can't be open rounds." Never word it as mutual exclusion.
- If asked to "fix" the backend to exclude max_rounds>0 from VEKN push: refuse — it would push nothing on the VEKN instance.
- The only correct "not pushed to VEKN" claim attaches to `self_organized_rounds`, not to `max_rounds > 0`.
- Disable logic: `ConfigTab.svelte:122-127` (started || pushedToVekn).
