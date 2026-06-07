---
name: finals-seed-order-uid-field
description: FinalsTable.seed_order is a list of player user_uids (top-5 seeding) — an easily-missed UID-bearing field in any per-player UID rewrite
metadata:
  type: project
---

`Tournament.finals.seed_order` (`models.py` FinalsTable) is a `list[str]` of **player user_uids** (the top-5 finals seeding order), NOT scores or labels. The engine builds it from standings `user_uid` (`engine/src/tournament/mod.rs` ~1578) and uses it for finals GW tie-breaking / seat-position logic (`scoring.rs` ~102-120, `mod.rs` ~1330, ~1625).

**Why:** it sits as a sibling of `finals.seating[].player_uid` and is trivially overlooked when remapping/renaming player UIDs — but it carries the same UIDs. Found during pst #15 offline go-online review: the structural temp→real UID remap walked `finals.seating[].player_uid` but skipped `finals.seed_order`, leaving dangling temp UIDs that silently corrupt finals scoring after reconciliation.

**How to apply:** when reviewing any code that rewrites, validates, or filters player UIDs across a Tournament (go-online remap, anonymization, merges, access-level projection), the full set of player-UID-bearing fields is: `players[].user_uid`, `rounds[][].seating[].player_uid`, `finals.seating[].player_uid`, **`finals.seed_order[]`**, `standings[].user_uid`, `raffles[].winners[]`, `winner`. NOT player UIDs (exclude from such rewrites): `seating[].judge_uid` and `override.judge_uid` are always the acting organizer/judge (`actor.uid`), never a temp/player UID. See [[tournament-transaction-nested-pool]] for the go-online txn context.
