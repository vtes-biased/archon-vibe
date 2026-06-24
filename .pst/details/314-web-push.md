# 314 — Web Push notifications (installed PWA → iOS/Android system notifications)

Separate from SSE (open-app only). Web Push wakes a backgrounded/closed PWA.
Branch: `worktree-web-push-314`.

## v1 product scope (PM ruling)

Exactly **two** push types — both low-frequency, high-signal (iOS forbids silent push, so
noisy = permission revoked):

1. **SEATING** → the *individual* seated player, on round start
   (`StartRound` / `SelfOrganizeRound` / `StartFinals`).
   Body: `"Round N — you're at Table X, seat Y."` (Finals: `"Finals — you're at the table, seat Y."`)
   Deep-link: their table in the tournament view. Subsumes "round started".
2. **ANNOUNCEMENT** → all tournament participants, on `POST /{uid}/announce`.
   Body = announcement text. Deep-link: announcements section.

**Deferred** (not v1): timer warnings (#277, would need a server-side timer source; noisiest/lowest-value),
re-seat pushes, sanction/DQ pushes (dignity + JG governs face-to-face), organizer-facing pushes.

**Opt-in UX:** gated behind live-tournament check-in. Primary surface = per-tournament inline
"Get notified when your table is ready" card (the Enable tap is the required user gesture).
Durable home = profile `AppSettings` toggle. iOS A2HS nudge: only iOS+Safari+not-installed+checked-in,
surfaced when they tap Enable in a non-standalone tab (intent-triggered, dismissible, ≤1 per tournament).
Privacy: push only committed seating (never draft/AlterSeating); participants of *that* tournament only.

## Architecture (principal-engineer ruling)

- **Storage:** backend-only `push_subscriptions(endpoint PK, user_uid, p256dh, auth, ua, created_at,
  last_seen_at)` in `schema.sql` — NOT an ObjectType, NOT in `objects`, NOT projected/synced (send
  credentials, never display data; projecting them would leak push keys). Parallels
  `auth_methods`/`avatars`/`oauth_*`. Index on `user_uid`. Add to the hard-delete purge path in `db.py`.
- **Sending (backend, not bot — bot has no DB):** `push_service.py`.
  - Pure `build_seating_payloads(updated_tournament, event_type) → [(user_uid, payload)]` — the one
    testable unit. **Seating-diff:** enumerate seats in the newly-appended round only
    (`updated.rounds[-1]` for StartRound/SelfOrganizeRound; `updated.finals.seating` for StartFinals).
    round_no = `len(updated.rounds)`; table = idx+1; seat = idx+1. Uniform across all three; one-pod
    SelfOrganizeRound naturally pushes only its 4–5 players. **Exclude `RestoreRound`** (no re-seat).
  - `send_to_users(user_uids, payload)`: query subs, fan out via `asyncio.to_thread(webpush, …)` under
    a bounded `Semaphore(~12)` (small VPS, pool max_size=20); prune row on **404/410 only** (not 429/5xx).
  - Fire post-commit as `asyncio.create_task` with self-contained try/except (mirror `_maybe_push_vekn`).
    **Never inside `tournament_transaction`** (DB-touching child task trips the `_acquire` owner guard).
- **Announcement fan-out:** `{p.user_uid for p in tournament.players if p.user_uid}` (existing idiom,
  tournaments.py 1122/1275/2045). No organizer special-case (sender has the composer open; org-only-
  not-playing simply isn't in `players`).
- **`pushsubscriptionchange` (no auth in SW):** v1 = **lazy reconcile** — SW re-subscribes locally; next
  app-open with auth re-POSTs current sub to authenticated `POST /api/push/subscribe` (upsert); stale
  rows pruned on next send (404/410). No unauthenticated rotate endpoint (endpoint-only rewrite = hijack).
  Unsubscribe = authenticated `DELETE /api/push/subscribe` (user is in-app when toggling off).
- **VAPID public key → frontend:** runtime `GET /api/push/vapid-key` (NOT build-time bake). The frontend
  ships as ONE release artifact to all envs (`.env.production`: "same CI artifact ships to all domains";
  `ansible/justfile build-frontend`), so a baked `VITE_VAPID_PUBLIC_KEY` would force beta+prod to share one
  VAPID keypair. A runtime endpoint lets each backend serve its own env's public key; fetched once on the
  online Enable gesture (subscribing requires network anyway, so no offline concern; not display data, so
  the "no API GET" rule doesn't apply). Private key + public key + `VAPID_SUBJECT` in env/ansible-vault,
  never committed. `just` keygen target. NOTE: rotating the keypair invalidates all existing subscriptions.
  (Deviates from PE ruling D, which assumed per-env frontend builds this repo doesn't do.)
- **SW handlers to add** (hand-written `service-worker.ts`, currently install/activate/fetch/message only):
  `push` → `event.waitUntil(showNotification(...))`; `notificationclick` → focus/open deep-link;
  `pushsubscriptionchange` → local re-subscribe. Push subs live in the browser push service, survive the
  version-keyed cache wipe on deploy.
- **Migration:** startup applies `schema.sql` idempotently — `CREATE TABLE/INDEX IF NOT EXISTS` is the
  whole migration. No runner.

## Implementation checklist

Backend
- [x] `schema.sql`: `push_subscriptions` table + `user_uid` index
- [x] `pyproject.toml`: add `pywebpush` (brings py-vapid); `uv lock`
- [x] VAPID config + keygen `just` target + `.env.example` + `vite-env.d.ts`
- [x] `db.py`: save/delete/get-by-users subscription fns + purge cleanup
- [x] `push_service.py`: pure payload builders + `send_to_users` (semaphore/to_thread/prune)
- [x] `routes/push.py`: `POST`/`DELETE /api/push/subscribe` (authed); register in `main.py`
- [x] `routes/tournaments.py`: seating push post-commit (excl RestoreRound) + announcement push post-commit

Frontend
- [x] `service-worker.ts`: push / notificationclick / pushsubscriptionchange handlers
- [x] `lib/stores/push.svelte.ts`: subscribe/unsubscribe/reconcile, permission state, key decode
- [x] `lib/api.ts`: registerPushSubscription / deletePushSubscription
- [x] `AppSettings.svelte`: notifications toggle (durable home)
- [x] per-tournament inline opt-in card + iOS A2HS nudge
- [x] `+layout.svelte`: reconcile subscription on app open (lazy-reconcile)
- [x] i18n: new strings × 5 locales

Docs
- [x] SYNC.md / ARCHITECTURE.md: push_subscriptions aux table + backend send path; PRODUCT.md scope

## Status

Code COMPLETE on `worktree-web-push-314`. Frontend `svelte-check` 0/0 + prod build green;
backend ruff green; `backend/tests/test_push_seating.py` (seating-diff invariant) 4/4 green.
Reviews: principal-engineer SHIP (all rulings verified), staff-frontend-engineer blocking
touch-target items fixed (Button + min-h-[44px]), senior-qa one test.

DEPLOY ENABLEMENT (separate follow-up ticket): the feature is a no-op until each env has a
VAPID keypair — `just vapid-keys`, private key + subject in ansible-vault, `VAPID_*` env wired
so `GET /api/push/vapid-key` serves the public key. Until then `is_configured()` is False and
no pushes send (graceful). iOS coverage requires the user to install the PWA (A2HS).
</content>
</invoke>
