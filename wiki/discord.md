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
3. General Information → Terms of Service and Privacy Policy URLs:
   `{site_url_base}/legal/terms` and `{site_url_base}/legal/privacy`. Discord
   surfaces them on the install consent screen, so an app without them asks a
   server owner to grant permissions with nothing to read first.
4. Installation → Default Install Settings: Guild Install, scopes `bot` and
   `applications.commands`, permissions `8861518864` (Manage Channels, Manage
   Roles, Manage Events, View Channels, Send Messages, Connect, Speak).

The organizer guide hands out the parameterless install link
`https://discord.com/oauth2/authorize?client_id={client_id}`, which carries no
scopes of its own: Discord derives them from step 4, so the link is inert until
those settings are saved. It is **hard-coded to the production app id** — one CI
frontend artifact ships to every domain (`frontend/.env.production`), so beta's
copy of the guide points at the production bot too.

Then in any server: Server Settings → Roles → a role → Links → Add requirement.
Members opt in through the server menu → Linked Roles → Connect.

Env: `DISCORD_CLIENTID`, `DISCORD_SECRET`, `DISCORD_REDIRECT_URI`,
`DISCORD_BOT_TOKEN`; `DISCORD_API_BASE` overrides the API host (defaults to the
real Discord — the backend test suite points it at a local fake).

**Alternatives considered and rejected** — bot direct role assignment needs a
per-server install and doesn't scale; webhooks for announcements are orthogonal to
Linked Roles; the Discord Social and Embedded App SDKs are native/games-only or
embed web apps *inside* Discord, the wrong direction.

## The tournament bot

A standalone process in `bot/` managing online tournaments inside Discord servers.
It is a **pure OAuth client** to the backend: no DB access, no business logic, no
role matrix of its own, and it never holds privileged backend credentials. All
mutations go through the same action endpoint using `event:run` tokens on
behalf of real users, and `/oauth/userinfo` reports the capabilities the holder
has, so `/sanction` simply surfaces the API's refusal. Single process only —
`sse_listener.py` holds module-level state.

**It is the first consumer of the per-event grant model**
([access](access.md#event-access-is-per-event)). Its token store is keyed
`(discord_id, tournament_uid)` and so is every API call, every refresh lock and
every SSE subscription; `/setup` and the player commands mint a fresh grant per
event, and the consent page names that event to the user. A member playing two
Discord tournaments authorizes once for each.

The bot therefore cannot claim a VEKN ID for a player: `/vekn/claim` merges two
accounts and answers with a **first-party** token pair, which no delegated grant
reaches. `/register` and `/checkin` send a member without a VEKN ID to their
Archon profile to link one, then back. On an event that requires a decklist,
`/checkin` warns only a player whose check-in found none on record; `/register`
and the check-in-open posts carry the neutral reminder.

**Status: pre-production.** Deployed and running, not yet live on production
guilds and not yet tested end to end.

**Deferred ask** — run Portal setup above against the production application
`1495034668469194864`, then install the bot on the production guild(s); which
servers count as production is part of the ask. Step 1 is believed already
done — the journal's `pushed metadata for user` lines can only come from a
working redirect — so confirm it rather than re-adding it. **Done when** Server
Settings → Roles → Links → Add requirement lists Archon with its three metadata
fields, and `/setup <tournament url>` in a production guild creates the category
with its announcement, lobby and judges channels.

**Trigger: the next production release** — and *by* it, not after it. That
release carries the organizer guide's install link, which is inert until step 4
is saved, so a release landing first hands every organizer a dead link.

**Commands** — `/setup <url>` probes the tournament's scoped SSE stream before
creating anything, so a bad or inaccessible uid, or a `Finished` tournament,
creates nothing; on success it names the category from the real tournament name and
creates announcement, lobby and judges channels, gated on the `create_tournament`
capability. Then `/teardown`, `/announce`, `/sync` (reconcile voice channels — a
repair tool), `/register`, `/checkin`, `/report <vp>` (the caller's live table,
the finals table first once one is seated), `/judge`, and a multi-step
`/sanction`. Guidance text names a command as a clickable Discord command
mention — `</name:id>`, the id read from the commands lightbulb synced at
startup — and falls back to the plain name when there is no synced id.

**Modules** — `token_store.py` (SQLite: tokens per (Discord account, event),
guild-tournament links with a scheduled event id, pending OAuth with a 15-minute
TTL carrying the event it is for); `archon_api.py`;
`sse_listener.py` (per guild-tournament SSE subscription); `channel_manager.py`;
`scheduled_events.py`; `oauth_callback.py`; `commands/`.

### The SSE listener

Subscribes to a **tournament-scoped** stream with the organizer's
`event:run` token, one connection per active guild-tournament pair,
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
The Finals voice channel stands until the tournament is finished, whatever the
finals table's own state — the engine sets no table-level result to gate on.

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
catch-up. Seating is also echoed into each table's own voice text chat, with
player mentions: every table on a round or finals start, only the tables whose
seating order changed on a mid-round update, and nothing on reconnect. It also
mirrors organizer in-app announcements, diffing the list by `id` and posting new
entries only.

**Round-timer posts** — every table's voice text chat gets the clock's story:
a start post when the organizer starts the round clock (a first start, never a
resume — the engine banks elapsed time in `elapsed_before_pause` on pause, so a
resume carries a non-zero value), 15-, 5- and 1-minute warnings, a time-up post,
and an extension post naming the granted and total extra time when a judge adds
time to that table ([rules §2.8](domain/tournament-rules.md#roles) requires the
extension to be clearly communicated). The start and extension posts are
edge-triggered diffs against the previous snapshot in the announcement layer, so
catch-up and reconnect never replay them. The warnings and time-up are a schedule:
a pure function mirrors the frontend countdown (`TimerDisplay.svelte`'s exact
formula: total − (elapsed before pause + since start) + extra time; the two must
stay in lockstep). One authority cancels and rebuilds the whole schedule on every
timer-signature change — start, pause, resume, per-table extra time, round change,
a table finishing — after every structural reconcile (including `/sync`), since a
channel created or repaired later than the clock start would otherwise keep a
schedule computed against its zero sentinel, and after a reconnect's catch-up.
There is no persisted cron: the schedule is recomputed from the snapshot. Passed
thresholds are suppressed without posting and a per-key fired set prevents
double-fire, so a restart never re-posts. Only pending tables get posts, and none
when the frontend hides the timer (untimed round, parallel rounds).

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

**OAuth flow** — `/setup` initiates PKCE, the user authorizes `event:run`
**for that tournament**, the local callback server receives the redirect, and the
token is stored in SQLite under that event for its API calls and SSE
subscription. Refresh clears the stored pair **only on 400/401**, an invalid
grant; 5xx, network errors and timeouts are treated as transient and feed the
listener's reconnect backoff instead, so a backend blip cannot kill a valid
token. A finished event is itself a 400, which is how a grant retires. A
successful callback respawns that event's dead listener — self-service recovery
once a token has genuinely died — and reconciles every guild linked to the
event: a fresh grant changes no tournament structure, so nothing else would give
the holder their table's CONNECT before the next round.

**Display names** — Register, AddPlayer and CheckIn accept an optional
`display_name` (the Discord nickname) stored on the player and shown in player and
seat displays. Bot-generated links point at `/consent?…&login_hint=discord`; an unauthenticated
user forwards to `/login?redirect=…&login_hint=discord`, which auto-redirects to
Discord OAuth. `/setup` and the player commands hand the link out as a Discord
**link button**, never as raw text: Discord caps a button URL at 512 characters,
and the production-shaped URL — frontend origin, bot callback, 32-character client
id, uuid, state and PKCE challenge — measures about 395, pinned by
`bot/tests/test_consent_link_button.py`.
