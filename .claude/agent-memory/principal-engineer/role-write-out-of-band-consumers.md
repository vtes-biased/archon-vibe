---
name: role-write-out-of-band-consumers
description: A User.roles write has two out-of-band consumers beyond the SSE frame — the Discord Linked Roles push (any role) and the resync nudge (IC/NC only); ops scripts and non-users.py writers silently skip both.
metadata:
  type: reference
---

`routes/users.py`'s role PATCH fires **two** side effects after `db.save_user`, and they
have *different* trigger conditions. Any other role writer (ops script, ETL, a new route)
must decide about both explicitly.

1. **Discord Linked Roles push** — `asyncio.create_task(sync_user_discord_roles(uid))` on
   *any* role delta. `roles_hook.build_metadata` maps PRINCE/NC/IC → `organization`,
   JUDGEKIN/JUDGE/RULEMONGER → `judge`, PT/PTC → `playtest`. It is push-on-change only:
   there is **no periodic reconciliation**, so a role granted out-of-band leaves Discord's
   auto-role metadata stale until the user re-links Discord or someone re-edits their roles.
   The call is safe to `await` from a script (no-ops when the user has no stored
   `discord_rc:` token, swallows its own exceptions).

2. **`broadcast_resync`** — only when `(old ∩ {NC, IC}) != (new ∩ {NC, IC})`, or an NC's
   country changes. `db.compute_access_version` hashes `_OVERLAY_ROLES = (IC, NC)` and
   nothing else, so granting Judge/Judgekin/Prince/PT/Ethics does **not** flip a viewer's
   fingerprint — no resync is needed or wanted for those.

Note the asymmetry: `roles` IS in `_USER_PUBLIC_FIELDS`, so *every* role change alters the
member (and sometimes public) projection **content** — that always rides the normal
`modified_at` since-delta. The fingerprint is about viewer *entitlement*, not object content;
don't conflate the two when reviewing "does this need a resync?".

Out-of-process writers additionally get no live SSE frame at all (broadcast is in-process),
and the stream has no lifetime cap — only keepalives — so already-connected clients see the
change on their next reconnect. Schedule such writes next to a backend restart if promptness
matters.
