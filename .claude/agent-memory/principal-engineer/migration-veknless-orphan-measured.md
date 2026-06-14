---
name: migration-veknless-orphan-measured
description: Measured prod-dump facts for the #169 vekn-ID-matching merge redesign — the vekn-less drop is NOT ref-free
metadata:
  type: project
---

Measured against the prod `archondb.dump.gz` (repo root, 19,003 members / 8,371 tournaments) on 2026-06-14 for the #169 merge redesign (vekn-ID matching replacing uid matching in `migrate_from_archon.py:merge_member`).

**Fact: dropping vekn-less legacy members is NOT reference-free.**
- 142 vekn-less members (19,003 total − 18,861 vekn-carrying; 0 source-duplicate vekn_ids → vekn-matching is a clean bijection).
- **9 tournament references point at vekn-less members: 4 in `players` dict + 5 in round seating `player_uid`**, concentrated in **3 Finished RICH tournaments** (rounds>0): "Granada Nocturna" (vekn 12784), "Neonate Revolution" (vekn 13209), "Granada by night: funeral wake" (no vekn id).
- 0 refs from: winner, finals_seeds, seating judge, tournament judges/organizers, coopted_by/sponsor, sanction judge, sanctions-on-member, league organizers.
- 0 player_uids reference a non-existent member row (every player resolves to a members or member_deletions row today → ETL-first with uid-preservation has 0 orphans, which is why #38 rehearsal passed clean).
- 24 distinct sanction-issuer (judge) uids, all are member rows → `issued_by_uid` is a member-uid ref the #169 remap MUST cover (build_sanction sets it at migrate_from_archon.py:622).

**Why:** #169's premise ("vekn-less members hold no tournament/deck refs because the engine requires a vekn_id for participants") is false for HISTORICAL data: old archon's `Register` event (`/Users/lpanhaleux/Developer/archon` events.py:64, `vekn: str = ""`) never enforced vekn_id; engine.py:136 stores the player unconditionally. The new engine's VeknIdRequired (engine/src/tournament/mod.rs:271) gates only the in-app path, which imported history bypasses.

**How it shipped (#169):** vekn-less members are seeded as soft-deleted shells
under their old uid (`seed_vekn_less_shell`), so the 9 refs resolve — a bare drop
was rejected for exactly the orphans measured here. Keep this fact for the
remaining prod runs (#39/#40): if a future change ever reconsiders dropping
vekn-less members, this is the counter-evidence. The orphan validator
(migrate_validate.py) catches a regression post-run (exact-uid existence scan),
but only after the bad write — a guard, not a fix.

Probe recipe (throwaway PG, never touches dev volume): `docker run -d --rm --name X -e POSTGRES_PASSWORD=etl -e POSTGRES_USER=etl -e POSTGRES_DB=archon_old -p 5544:5432 postgres:17`; dump is PLAIN SQL (`gunzip -c archondb.dump.gz | psql`, not pg_restore); "role archon does not exist" lines are harmless ownership noise.
