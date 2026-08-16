# Discord

Two independent integrations: **Linked Roles**, a backend feature pushing VEKN
role metadata to Discord, and the **tournament bot**, a separate process running
online events inside Discord servers.

## Linked Roles

VTES Discord servers carry roles mirroring VEKN roles, traditionally managed by
hand. Discord's Linked Roles feature lets the app push per-user metadata so Discord
auto-assigns roles **across every server** using the connection — no bot install
per server.

1. The app registers role-connection metadata fields with Discord, once and
   idempotently, at startup.
2. A user authorizes the app once via OAuth2 with the `role_connections.write`
   scope.
3. The app pushes the user's metadata to
   `PUT /users/@me/applications/{app_id}/role-connection`.
4. Server admins create roles gated on that metadata, and Discord assigns and
   removes them.

Three `INTEGER_GREATER_THAN_OR_EQUAL` fields:

| Key | Shown as | Values |
|---|---|---|
| `organization` | VEKN Role | 1 Member · 2 Prince · 3 NC · 4 IC |
| `judge` | Judge Level | 1 Sheriff · 2 Judge · 3 Rulemonger |
| `playtest` | Playtest Role | 1 Playtester · 2 Playtest Coordinator |

The builder takes the **max** matching level per axis and falls back to
`organization = 1` for any user with a `vekn_id` but no organization role, so
admins can build "Prince" as `organization >= 2`, "VEKN Member" as
`organization >= 1`. The rare Ethics role is assigned by hand. The user's Discord
profile shows `platform_name = "Archon"` and
`platform_username = vekn_id or name`.

**The push requires the target user's own OAuth token** with
`role_connections.write` — the backend cannot push for a user who has never logged
in through Discord, so metadata is only pushed when a stored token exists. It fires
fire-and-forget on Discord login and link, on role changes, on VEKN-ID changes, and
on periodic sync. Registration at startup needs `DISCORD_BOT_TOKEN`, which must
belong to the **same application** as `DISCORD_CLIENTID`.

**Portal setup**, once per app and environment:

1. OAuth2 → Redirects: add `{site_url_base}/auth/discord/callback`, matching
   `DISCORD_REDIRECT_URI` exactly.
2. General Information → Linked Roles Verification URL:
   `{site_url_base}/auth/discord/authorize` — the **plain** authorize endpoint. A
   cold click from Discord carries no session, so the URL must log the user in
   *and* push metadata; the `?link=true` variant is only for an already
   authenticated profile link and would 401 here.

Then in any server: Server Settings → Roles → a role → Links → Add requirement.
Members opt in through the server menu → Linked Roles → Connect.

Env: `DISCORD_CLIENTID`, `DISCORD_SECRET`, `DISCORD_REDIRECT_URI`,
`DISCORD_BOT_TOKEN`.

**Alternatives considered and rejected** — bot direct role assignment needs a
per-server install and doesn't scale; webhooks for announcements are orthogonal to
Linked Roles; the Discord Social and Embedded App SDKs are native/games-only or
embed web apps *inside* Discord, the wrong direction.

## The tournament bot

A standalone process in `bot/` managing online tournaments inside Discord servers.
It is a **pure OAuth client** to the backend: no DB access, no business logic, no
role matrix of its own, and it never holds privileged backend credentials. All
mutations go through the same action endpoint using `user:impersonate` tokens on
behalf of real users, and `/oauth/userinfo` reports the capabilities the holder
has, so `/sanction` simply surfaces the API's refusal. Single process only —
`sse_listener.py` holds module-level state.

**Status: pre-production.** Deployed and running, not yet live on production
guilds and not yet tested end to end.

**Commands** — `/setup <url>` probes the tournament's scoped SSE stream before
creating anything, so a bad or inaccessible uid, or a `Finished` tournament,
creates nothing; on success it names the category from the real tournament name and
creates announcement, lobby and judges channels, gated on the `create_tournament`
capability. Then `/teardown`, `/announce`, `/sync` (reconcile voice channels — a
repair tool), `/register`, `/checkin`, `/report <vp>`, `/judge`, and a multi-step
`/sanction`.

**Modules** — `token_store.py` (SQLite: tokens, guild-tournament links with a
scheduled event id, pending OAuth with a 15-minute TTL); `archon_api.py`;
`sse_listener.py` (per guild-tournament SSE subscription); `channel_manager.py`;
`scheduled_events.py`; `oauth_callback.py`; `commands/`.

### The SSE listener

Subscribes to a **tournament-scoped** stream with the organizer's
`user:impersonate` token, one connection per active guild-tournament pair,
delivering only that tournament, its sanctions and its judge calls — see
[sync](sync.md#the-sse-endpoint).

`reconcile_channels` is the **sole idempotent authority** creating and deleting
voice channels and setting per-member CONNECT+SPEAK permissions, called on every
relevant state change — round start and end, finals, reconnect, `/sync`. A pure
function computes the target set and a structure-signature hash guards it, so a
reconcile is skipped when the structure is unchanged. A per-tournament
`asyncio.Lock` serializes structural mutations, so concurrent events, reconnects
and `/sync` never interleave. Convergence diffs Discord's **actual** channels —
one `fetch_guild_channels` call, matched by name — against the desired set, so a
timed-out partial create converges on retry instead of duplicating channels.

**Event dispatch is time-bounded** (`_DISPATCH_TIMEOUT`): a handler that blocks
would freeze stream consumption silently — no error and no reconnect, since
`sock_read` never fires while dispatch is stuck. The bound turns a permanent wedge
into a logged skip that the next reconcile repairs.

**Teardown order** — Discord *un-parents* a child channel to the guild root when
its category is deleted; it never cascades. So teardown deletes the category last,
only once every child is confirmed gone, and `extra_channel_ids` catches channels
that drifted out of the category in an earlier partial teardown.

**#judges privacy** — private from creation, with `@everyone` denied VIEW_CHANNEL
and CONNECT. Every reconcile syncs its membership to the `/setup` runner plus the
tournament's organizers, so a web-app organizer change propagates automatically. It
falls back to the backend `discord_id` delivered on the scoped stream's participant
frames for organizers who never ran `/register`, posting a one-time notice for
anyone still unresolved. The structure signature keys on the organizer set
directly, so this reconciles in every state and not just during play, and the same
sync retrofits pre-privacy channels found without the deny override.

**Announcements** are a separate edge-triggered layer posting seating, standings and
scores to #announcement after the structural reconcile, suppressed during silent
catch-up. It also mirrors organizer in-app announcements, diffing the list by `id`
and posting new entries only.

**Round-timer reminders** — a pure function mirrors the frontend countdown
(`TimerDisplay.svelte`'s exact formula: total − (elapsed before pause + since
start) + extra time; the two must stay in lockstep) to
schedule 15-minute and 5-minute warnings plus a time-up task per table, posting into
each table's voice text chat. One authority cancels and rebuilds the whole schedule
on every timer-signature change — start, pause, resume, per-table extra time, round
change, a table finishing — and after a reconnect's catch-up. There is no persisted
cron: the schedule is recomputed from the snapshot. Passed thresholds are suppressed
without posting and a per-key fired set prevents double-fire, so a restart never
re-posts. Only pending tables get reminders.

**Catch-up on connect** — the bot sends no `since` cursor, so the backend replays
full current state; events seed state silently until `sync_complete` flips the
synced flag, so a restart never re-posts past announcements. A `resync` message
triggers a fresh reconnect. A shared aiohttp session spans reconnects, and
module-level state is cleaned up on stop and teardown.

**Channel permissions** — #announcement denies SEND_MESSAGES to `@everyone` with
the bot allowed; table voice denies CONNECT to `@everyone` and allows
CONNECT+SPEAK to each seated player plus organizers, who may join any table to
judge; #judges denies VIEW_CHANNEL and CONNECT to `@everyone` and allows the bot
and organizers. All synced idempotently.

**Scheduled events** — one Discord EXTERNAL Guild Scheduled Event per linked online
tournament, driven off the SSE snapshot with no setup-time create path: created on
catch-up reconnect, idempotent across restarts via the persisted event id, edited on
every relevant change (name, start, finish, banner), deleted on finish or teardown.
The cover image is the tournament banner transcoded webp→PNG. It needs the
**MANAGE_EVENTS** bot permission and degrades gracefully without it, logging and
posting a one-time hint to #judges.

**OAuth flow** — `/setup` initiates PKCE, the user authorizes `user:impersonate`,
the local callback server receives the redirect, and the token is stored in SQLite
for all API calls and SSE subscriptions. Refresh clears the stored pair **only on
400/401**, an invalid grant; 5xx, network errors and timeouts are treated as
transient and feed the listener's reconnect backoff instead, so a backend blip
cannot kill a valid token. A successful `/register` callback respawns any dead
listeners for that organizer's guild links — self-service recovery once a token has
genuinely died.

**Display names** — Register, AddPlayer and CheckIn accept an optional
`display_name` (the Discord nickname) stored on the player and shown in player and
seat displays. `/auth?login_hint=discord` auto-redirects bot-generated links to
Discord OAuth.
