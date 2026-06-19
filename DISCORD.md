# Discord Linked Roles Integration

## Context

VTES Discord servers have roles mirroring Archon roles (NC, Prince, Judge, PT, etc.)
traditionally managed by hand. Discord's **Linked Roles** feature lets Archon push
per-user metadata so Discord auto-assigns roles **across every server** that uses the
connection — no bot install per server. The tournament-running Discord bot (`bot/`) is a
separate concern.

## How Linked Roles work

1. Archon registers role-connection metadata fields with Discord (one-time, idempotent).
2. A user authorizes Archon once via OAuth2 with the `role_connections.write` scope.
3. Archon pushes the user's metadata via `PUT /users/@me/applications/{app_id}/role-connection`.
4. Server admins create roles gated on that metadata; Discord auto-assigns/removes them.

## Metadata (as shipped)

Three `INTEGER_GREATER_THAN_OR_EQUAL` fields — `roles_hook/__init__.py` `METADATA`:

| Key | Shown in Discord as | Values |
|-----|---------------------|--------|
| `organization` | VEKN Role | 1 Member · 2 Prince · 3 NC · 4 IC |
| `judge` | Judge Level | 1 Judgekin · 2 Judge · 3 Rulemonger |
| `playtest` | Playtest Role | 1 Playtester · 2 Playtest Coordinator |

`build_metadata()` takes the **max** matching level per axis, and falls back to
`organization = 1` (Member) for any user who has a `vekn_id` but no org role. Admins then
build roles like "Prince" → `organization >= 2`, "Judge" → `judge >= 2`, "VEKN Member" →
`organization >= 1`. The rare Ethics role is assigned by hand.

The user's Discord profile shows `platform_name = "Archon"`,
`platform_username = vekn_id or name` (`build_platform_info()`).

## Implementation

- `backend/src/roles_hook/__init__.py` —
  `register_metadata()` (idempotent `PUT …/role-connections/metadata` with the **bot
  token**, on startup), `push_role_metadata()` (per-user `PUT` with the user's **OAuth
  token**), `refresh_discord_token()`, and `sync_user_discord_roles()` (refresh-then-push,
  fire-and-forget safe).
- `backend/src/main.py` — calls `register_metadata()` on startup when `DISCORD_CLIENTID`
  is set.
- `backend/src/routes/auth/discord.py` — the OAuth flow requests
  `identify email role_connections.write`; on login/link it stores the user's tokens in
  the transient-token store (key `discord_rc:{uid}`, 365-day) and pushes current metadata.
- Role changes re-push fire-and-forget via `sync_user_discord_roles(uid)`
  (`routes/vekn.py`, `routes/users.py`).
- Frontend entry points: "Login with Discord" (`routes/login`) and the profile
  "Link Discord" button (`routes/profile`, `link=true`).

## Discord Developer Portal setup (one-time per app / environment)

1. **OAuth2 → Redirects**: add `{site_url_base}/auth/discord/callback` (must match
   `DISCORD_REDIRECT_URI` exactly).
2. **General Information → Linked Roles Verification URL**: set to
   `{site_url_base}/auth/discord/authorize`.
   Use the **plain** authorize endpoint — a cold click from Discord carries no Archon
   session, so the URL must log the user in *and* push metadata. The `?link=true` variant
   is only for an already-authenticated profile link and would 401 here.
3. `DISCORD_BOT_TOKEN` must belong to the **same application** as `DISCORD_CLIENTID`
   (registration is `applications/{client_id}/role-connections/metadata` authed with
   `Bot {token}`).

Then, in any server: Server Settings → Roles → a role → **Links → Add requirement** →
pick the app → set criteria. Members opt in via the server-name menu → **Linked Roles →
Connect**.

Prod cutover repeats steps 1–2 against the production domain (`archon.vekn.net`).

## Environment variables

```
DISCORD_CLIENTID      # OAuth client id (also the role-connection app id)
DISCORD_SECRET        # OAuth client secret
DISCORD_REDIRECT_URI  # {site_url_base}/auth/discord/callback
DISCORD_BOT_TOKEN     # bot token of the SAME app — for metadata registration
```

## Discord API endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `PUT /applications/{app_id}/role-connections/metadata` | Bot token | Register schema (idempotent, startup) |
| `PUT /users/@me/applications/{app_id}/role-connection` | User OAuth token | Push per-user metadata |
| `POST /oauth2/token` | Client creds | Token exchange & refresh |

## Alternatives explored (not pursued)

- **Bot direct role assignment**: per-server install, doesn't scale — covered by the
  separate `bot/` project.
- **Webhooks for announcements**: simple `POST` to a URL, but orthogonal to Linked Roles;
  could be added to tournament config later.
- **Discord Social SDK / Embedded App SDK**: native/games-only, or embeds web apps *inside*
  Discord — wrong direction.

## References

- [Linked Roles tutorial](https://docs.discord.com/developers/tutorials/configuring-app-metadata-for-linked-roles)
- [Role Connection Metadata API](https://discord.com/developers/docs/resources/application-role-connection-metadata)
- [Discord OAuth2 docs](https://docs.discord.com/developers/topics/oauth2)
