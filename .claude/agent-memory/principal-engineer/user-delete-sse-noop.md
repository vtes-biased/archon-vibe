---
name: user-delete-sse-noop
description: Frontend SSE handler intentionally PERSISTS soft-deleted users (saves the deleted_at row) instead of removing them; list queries filter deleted_at
metadata:
  type: project
---

`sync.ts` SPECS `users` `del` was historically a no-op. As of pst #77 it is wired to SAVE the soft-deleted payload, not hard-delete: `del: async (_uid, item) => { if (item) await saveUser(item); }`. `ObjectSpec.del` was widened to `(uid, item?)` and both the live single-event path and the batch flush path now pass the full item.

**Why:** A soft-deleted user (e.g. the dying account from `merge_users`) may still be referenced by tournament `players` entries. Hard-deleting it would break `getUser(uid)` resolution for those refs (and SSE ordering isn't guaranteed). So the row is kept (carrying `deleted_at`) for by-uid resolution, and excluded from listings instead.

**How to apply:** Soft-deleted users are filtered out of the three list/search surfaces only — `getAllUsers`, `getUsersByCountry`, `getFilteredUsers` (all in `db.ts`, each does `.filter(u => !u.deleted_at)`). By-uid reads (`getUser`, and the offline-rescue batch read, see [[destructive-store-wipe-offline-rescue]]) deliberately still return soft-deleted rows so player references render. If you add a new user-LISTING query, add the `deleted_at` filter; if you add a by-uid resolver, do NOT filter. Other `del` specs (sanctions/tournaments/decks/leagues) are bare `deleteX(uid)` and harmlessly ignore the extra `item` arg.
