# #185 — SSE silent auth-downgrade (backend keystone + client refresh)

Surfaced during #91 beta: a bot restart did not recreate tournament round-1
channels. Root cause is **not** #182 (handler-stall wedge + seed-only catch-up,
both fixed). It is a distinct, lower-level bug that also bites the **webapp**.

## The bug

Token-optional SSE endpoints cannot distinguish *"no token → anonymous"* from
*"token present but invalid/expired"* and silently choose the **public**
projection for both:

- `main.py:_resolve_user_from_token` decodes the JWT inside a bare
  `try/except Exception: return None` — an expired/invalid token resolves to
  `None`, identical to no token at all.
- `broadcast.entitled_level(None, …) → "public"`.
- `/stream` (and `/snapshot`) then return **HTTP 200** with the public
  projection. For a tournament, `_TOURNAMENT_PUBLIC_FIELDS` (`access_levels.py`)
  omits `rounds`, `finals`, `players`, `standings`, `checkin_code`, etc. — only
  `member`/`full` carry them (SYNC.md "Tournament Field Visibility").

### Victim A — the bot (the observed symptom)

**CORRECTED root cause (post-implementation review).** The bot's credential was
never read at all — not an expiry problem. The bot sends `Authorization: Bearer`
(`sse_listener.py:183`), but `/stream` + `/snapshot` read the credential only
from the `token=` query param (`stream_updates`/`get_snapshot` signatures), which
the bot never sends. So `_resolve_user_from_token(None)` → None → public for the
bot **always, regardless of token validity** — `rounds=0` → `_reconcile` (gated on
`obj.get("rounds")`, `sse_listener.py:946`) creates nothing. Observed log:
`Snapshot: state=Playing rounds=0`. The bot's authed SSE had in fact never
resolved a user. (The expired-token theory below holds for the *webapp*, which
does use the query param; for the bot it was a red herring.)

Fix: `/stream` + `/snapshot` now resolve the `Authorization` header too, via the
revocation-aware `get_current_user` (handles `oauth_access` + the bot's
`user:impersonate` scope), and still 401 a supplied-but-invalid credential. The
bot's proactive refresh + 401 path are now meaningful (the backend finally reads
its token). Token-lifetime context: OAuth access token TTL = **1 h**
(`oauth.py:50`), refresh token = 30 d.

### Victim B — the webapp (the bug nest)

- Access token TTL = **15 min** (`_tokens.py:17`); refresh token = **7 d**
  (`_tokens.py:18`).
- Freshness depends solely on a **`setTimeout`** armed 1 min before expiry
  (`auth.svelte.ts:89-106`). `setTimeout` is throttled/paused under tab-suspend
  and device-sleep.
- `getAccessToken()` returns the raw localStorage token with **no expiry check**
  (`auth.svelte.ts:133`).
- SSE uses **native `EventSource`** (`sync.ts:248`) with `token=` in the URL; on
  error → `handleError()` → `connect()` → re-reads `getAccessToken()`
  (`sync.ts:243`).

Real-world trigger: laptop sleeps >15 min → timer didn't fire, token expired →
on wake the dropped connection reconnects with the **stale** token → backend
200 + public → catch-up `spec.save()`s public rows over IndexedDB. A `since=`
reconnect overwrites only *changed* rows → an IndexedDB **mix** of member +
public projections; a `force_resync`/first-connect downgrades the whole corpus.
The user still shows logged-in, with **no error**. The personal overlay
(own profile/decks at full) silently stops.

## Design principles (from SYNC.md)

1. **We do not force auth.** `public` (no token / no vekn_id) is a first-class
   level. Anonymous browsing is supported and correct.
2. **A logged-out user = anonymous = public**, reached via the **resync**
   mechanism: clear all IndexedDB stores + cursor, then refill at public
   (SYNC.md §Resync; the existing logout-in-another-tab path,
   `auth.svelte.ts:156`). A level change is always **clear-then-refill**, never
   a partial overlay.
3. Therefore: an expired **access** token is **not** a logout (the 7-day refresh
   token is almost always still valid). The correct reaction is **refresh and
   stay at the user's real level**, not drop to public.

## The fix

### 1. Backend — keystone (single source of truth)

In `stream_updates` (and `get_snapshot`): distinguish *absent* from
*present-but-unresolved* token. When a `token` is supplied but resolves to
`None`, return **401**; serve public only when no token is present.

```python
stream_user = await _resolve_user_from_token(token)
if token and stream_user is None:
    raise HTTPException(401, "Invalid or expired token")
```

This turns a silent corruption into a detectable signal for every client.
(Decision point for principal-engineer: apply to the unscoped browser stream
too, or scope to the bot's `tournament is not None` first? Applying to both is
cleaner and is the goal — but it **requires** the webapp change below to land
together, because native `EventSource` can't read a 401 and won't
auto-reconnect-with-refresh on its own.)

### 2. Bot — already wired

`resp.status == 401 → refresh → retry` exists (`sse_listener.py:165`). Works the
moment the backend 401s. Belt-and-suspenders: proactively refresh when the
stored `expires_at` is past *before* opening the stream, to avoid one failed
connect per restart.

### 3. Webapp — refresh, don't log out

Principle: **never open SSE with a known-stale token while a valid refresh token
exists; never change levels except through a full resync.**

- **Before each (re)connect**: if the access token is expired / within the
  refresh threshold, `await refreshTokens()` first, then build the URL. Removes
  the dependency on the fragile `setTimeout` for the SSE path (timer stays as an
  optimization). Cleanest as an async `getValidAccessToken()` that refreshes
  on demand, awaited in `connect()`.
- **On a backend 401**: treat as stale access token → refresh → reconnect.
  Still not a logout.
- **Anonymous only when the refresh token itself is dead** (genuine 7-day
  session end) → the existing logout path: clear tokens → `syncManager.refresh()`
  → resync clears IndexedDB and refills public. Explicit, documented, no mix.
- **Transient refresh failure** (network/server restart): do **not** clear
  tokens, do **not** connect with the stale token — stay disconnected and back
  off (mirrors the existing `scheduleRefresh(5)` retry).
- A successful refresh should trigger an SSE reconnect so an already-downgraded
  stream self-heals at the correct level.

Role/vekn_id changes while away are orthogonal — `resync_after` already forces a
`{"type":"resync"}` on reconnect (SYNC.md §Resync), so level *changes* are
handled by clear-then-refill regardless.

## Acceptance

- Backend: token present + invalid/expired → 401 on `/stream` and `/snapshot`;
  no token → 200 public unchanged. (Test: expired JWT → 401; absent → 200
  public; valid member → member projection includes `rounds`.)
- Bot: after access-token expiry, a reconnect refreshes and the scoped stream
  delivers `full`/`member` (rounds present) → `_reconcile` recreates round
  channels. No silent public consumption.
- Webapp: simulate token expiry across a reconnect (e.g. clock skew / forced
  expiry) → the client refreshes and stays at its level; IndexedDB never holds a
  member+public mix; a truly dead refresh token drops to anonymous via a clean
  resync (no partial overlay), with a visible state (not silent).
- Regression net: a logged-out user still browses at public (anonymous remains
  first-class).

## Notes

- Same symptom as #182 (no round-1 channels) but a different layer — #182 fixed
  the wedge + made channel setup idempotent/self-healing; #185 fixes *why* the
  self-heal saw `rounds=0` (degraded projection from a stale token).
- Matters for prod **#39** (more data, `VEKN_PUSH=true`, real users on flaky
  mobile networks where token-expiry-across-reconnect is common).
- Touches the sync/access path → principal-engineer review before implementing.

## Implementation (2026-06-14)

- **Backend** (`main.py`): new `_resolve_viewer(request, token, authorization)`
  shared by `/stream` + `/snapshot` — resolves the `Authorization` header via the
  revocation-aware `get_current_user` (the bot) OR the `token` query param via
  `_resolve_user_from_token` (browser EventSource). A supplied-but-invalid
  credential of either form → 401 (header path raises via `get_current_user`'s
  expired/invalid/revoked handlers; query path raises with `Cache-Control:
  no-cache`). No credential → anonymous/public unchanged. This is what actually
  fixes the bot (its header was previously ignored).
- **Frontend** (`auth.svelte.ts`): `refreshTokens()` now single-flight (shared
  in-flight promise wrapping `doRefreshTokens()`); new `ensureSyncToken()` →
  `{token|anonymous|downgrade|retry}` (refresh-on-demand; cleared-vs-kept tokens
  distinguish downgrade from retry).
- **Frontend** (`sync.ts`): `connect()` resolves `ensureSyncToken()` up front,
  re-checks the epoch after the await, routes `retry`→`handleError()` backoff and
  `downgrade`→`refresh()` (clear-then-refill); one token feeds both snapshot +
  stream. `fetchSnapshot(epoch, token)` refresh+retries once on 401.
- **Bot** (`sse_listener.py`): `_access_token_expired()` (unverified JWT `exp`
  decode) drives a proactive refresh before connecting; 401 path stays backstop.
- **Tests**: `backend/tests/test_stream_auth.py` — 4 interface-bound tests (no
  mocks): `/stream` rejects an invalid query token AND an invalid Bearer header
  (the bot path — pins that the header is read at all); `/snapshot` rejects an
  invalid token; `/snapshot` allows anonymous (not 401). Bot single-flight
  already covered by `bot/tests/test_refresh_single_flight.py`.
- **Gates**: backend ruff + auth-gate (4) + regression spot-check green; bot ruff
  + 7 tests; frontend svelte-check 0 errors.

## principal-engineer review (2026-06-14)

**Verdict: SOUND** — proceed. Every link in the chain verified against code. Two
decisions tightened + guardrails below; design is otherwise correct.

**Resolved decisions:**
- **Backend 401 covers BOTH `/stream` and `/snapshot`, including the unscoped
  browser stream** (scoping to the bot would leave the worse bug — the webapp
  IndexedDB mix — unfixed). **Load-bearing precondition: the backend 401 and the
  webapp refresh-on-demand MUST land in the same change** — native `EventSource`
  can't read a 401 and would otherwise reconnect-loop (capped at
  `maxReconnectAttempts=5` then stuck disconnected). Confirmed one ticket, not
  split.
- **401 is the right mechanism**, not an in-band `{"type":"auth_expired"}` frame:
  401 preserves the "serve no projection on a bad token" invariant; reserve the
  SSE in-band channel (`resync`) for post-connection state changes. The 401 is
  safe precisely because refresh-on-demand makes a stale-token 401 a rare
  backstop (clock skew / refresh-in-flight), not the steady-state path.

**Required implementation guardrails:**
1. **Epoch race** — `getValidAccessToken()` adds an `await` after `epoch` is
   captured in `connect()`; add `if (this.superseded(epoch)) return;`
   immediately after the refresh await (before `new EventSource`, `sync.ts:248`).
2. **Single-flight refresh** — `refreshTokens()` (`auth.svelte.ts:234`) has NO
   single-flight guard; the connect-time refresh + the proactive timer + a
   cross-tab refresh can double-POST and trip refresh-token reuse-detection.
   Add an in-flight-promise cache (mirror the bot's `archon_api.py:88-101`).
   Important if the backend rotates+reuse-detects refresh tokens — verify.
3. **`/snapshot` fall-through** — `fetchSnapshot` (`sync.ts:137-140`) treats any
   non-`ok` as null→fall-through to SSE; must branch on **401 → refresh+retry**
   before the null path (else it falls through to a stream connect with the same
   stale token).
4. **Three-outcome decision function** for the webapp's stale/401 reaction, made
   explicit: refresh-ok (same level) → reconnect **keeping** the cursor (let the
   server's `resync_after` decide if a level-change resync is needed — do NOT
   self-clear the cursor); refresh-dead → `syncManager.refresh()` (anonymous,
   clear-then-refill); transient failure → backoff, keep cursor + tokens, never
   connect stale.

**New findings (added to scope):**
- **Calendar `.ics` feed is explicitly OUT of scope** (`routes/calendar.py:124`):
  its `calendar_token` is a long-lived secret polled by external apps that can't
  refresh and hold no IndexedDB — degrade-to-public on a bad token is *correct*
  there. It uses a separate resolver (`get_user_by_calendar_token`) so it's
  naturally untouched — do NOT unify the two resolvers behind the 401 rule. The
  rule is per-client-contract (refreshable consumer with a projection-consistent
  local store), not "every token-optional endpoint."
- **Bot proactive refresh is promoted from optional → recommended** for #39:
  once the backend 401s the bot self-heals, but eats one failed connect + backoff
  per restart/expiry; on flaky mobile with `VEKN_PUSH=true` that's a window with
  missing round channels. Refresh when stored `expires_at` is past *before*
  `session.get` (`sse_listener.py:156`). 401 makes it correct; proactive makes
  it prompt — do both.
- **Security: hardening, not regression** — expired creds get served *less*,
  never more, so no escalation. 401 body fires identically for
  malformed/expired/unknown-sub (no user-existence leak). **Set
  `Cache-Control: no-cache` on the 401 response** (as `/snapshot` already does at
  `main.py:526`) so no nginx/CDN layer pins a 401 for an anon viewer.
- **Personal overlay** (full-on-top-of-member for own/role objects) is the only
  other multi-level write, but it's intentional/idempotent (same uid, strictly
  higher level) and only runs on an authed connection — the 401 fix protects the
  one case where it would silently stop. No other projection-mix path.

**Tests (one-per-invariant bar):** the 3 backend cases in Acceptance are the
correct minimal set. Add (1) a frontend test that a `since=` reconnect after a
simulated expiry never leaves a member+public mix in IndexedDB (assert no row is
below the viewer's entitlement post-reconnect — the actual corruption
invariant); (2) a single-flight assertion (concurrent `getValidAccessToken()` +
timer → exactly one refresh POST). Skip a bot integration test (the 401→refresh
path is covered by existing reconnect logic).

**Concrete file:line targets:** `main.py:480-495` (the swallow; raise 401 at
both callers `:507`/`:754`, set `Cache-Control: no-cache`); `sync.ts:243`
(`await getValidAccessToken()` + epoch re-check); `sync.ts:137-140` (snapshot
401 branch); `auth.svelte.ts:234` (single-flight); `auth.svelte.ts:97` (timer
stays as optimization only); `sse_listener.py:156` (bot proactive refresh);
`routes/calendar.py:124` (explicitly untouched).
