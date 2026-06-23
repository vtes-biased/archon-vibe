---
name: config-field-create-updateconfig-asymmetry
description: A tournament config field must be added to BOTH create_tournament's object literal AND UpdateConfig's config_fields array; table_rooms is a live instance of the gap
metadata:
  type: project
---

A new tournament config field lives in two engine sites that must stay in sync:
`create_tournament`'s `json::object!` literal (`engine/src/tournament/mod.rs` ~99-131)
AND the `UpdateConfig` `config_fields` array (~2093). A field present in only one is a
latent bug: settable-then-unreadable on create, or default-only on create then settable
on update.

**Live instance:** `table_rooms` is in `config_fields` (mod.rs ~2113) but absent from the
`create_tournament` literal — so it can be UpdateConfig'd but isn't initialized at create.
Don't replicate this when adding fields (e.g. `self_organized_rounds`).

Shared validation belongs in `validate_config_fields` (~47), which both create and
UpdateConfig call — put cross-field rules (e.g. "X only when max_rounds > 0") there once,
not duplicated per handler.

**Why:** caught reviewing #274 (self-organized rounds). The two-site requirement is
non-obvious — `config_fields` looks like the single source of truth but the create literal
is a parallel hardcoded list.
**How to apply:** when any review adds/renames a tournament config field, grep BOTH the
create literal and `config_fields`; flag a field in only one. See also [[update-config-field-projection-check]].
