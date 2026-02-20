# Discord Linked Roles Integration

## Context

VTES Discord servers have roles mirroring Archon roles (NC, Prince, Judge, PT, etc.) currently managed manually. Discord's **Linked Roles** feature lets Archon push user metadata so Discord auto-assigns roles across all servers — no bot per server needed.

A separate Discord bot for running online tournaments inside Discord servers is planned independently.

## Current State

- Discord OAuth exists (`identify email` scopes) — `backend/src/routes/auth.py`
- `AuthMethod` model supports `discord` type — `backend/src/models.py`
- Roles: IC, NC, Prince, PTC, Rulemonger, Judge, Judgekin, Ethics, PT, DEV

## How Linked Roles Work

1. Archon registers up to **5 metadata fields** with Discord
2. User connects once: Discord Settings > Connections > Archon (OAuth2 with `role_connections.write` scope)
3. Archon pushes metadata via `PUT /users/@me/applications/{app.id}/role-connection`
4. Discord auto-assigns/removes roles based on admin-configured criteria — **across every server** using the connection

## Metadata Design (hierarchical encoding)

| Field | Type | Values | Discord criteria |
|-------|------|--------|-----------------|
| `admin_level` | `INTEGER_GTE` | 0=none, 1=Prince, 2=NC, 3=IC | `>= 1` → Prince+, `>= 2` → NC+ |
| `judge_level` | `INTEGER_GTE` | 0=none, 1=Judgekin, 2=Judge, 3=Rulemonger | `>= 2` → Judge+ |
| `pt_level` | `INTEGER_GTE` | 0=none, 1=PT, 2=PTC | `>= 1` → any PT |
| `is_member` | `BOOLEAN_EQUAL` | has VEKN ID | `== true` → verified member |
| `member_since` | `DATETIME_LTE` | account/VEKN creation date | `<=` → "member for at least X" |

Server admins create roles like: "Prince" → `admin_level >= 1`, "NC" → `admin_level >= 2`, "Judge" → `judge_level >= 2`, "VEKN Member" → `is_member == true`. Ethics role is rare enough to handle manually.

## Implementation Plan

### 1. Add `discord_tokens` to AuthMethod model

`backend/src/models.py` — add encrypted token fields:

```python
class AuthMethod(msgspec.Struct, kw_only=True):
    # ... existing fields ...
    discord_refresh_token: str | None = None  # Encrypted Discord OAuth2 refresh token
    discord_token_expires_at: datetime | None = None
```

Currently AuthMethod stores only `identifier` (discord user ID) and no `credential_hash` for Discord. We'll store the encrypted refresh token in `discord_refresh_token`. The access token is short-lived and fetched on demand via refresh.

### 2. Extend Discord OAuth flow

`backend/src/routes/auth.py` — two changes:

**a) Add `role_connections.write` scope** to the OAuth URL:

```python
# Current:  "scope": "identify email"
# New:      "scope": "identify email role_connections.write"
```

**b) Store Discord refresh token** in the callback handler:

After the token exchange (`POST /oauth2/token`), `discord_tokens` includes `refresh_token`. Store it on the AuthMethod:

```python
auth_method.discord_refresh_token = encrypt(discord_tokens["refresh_token"])
auth_method.discord_token_expires_at = now + timedelta(seconds=discord_tokens["expires_in"])
```

Encryption: use `cryptography.fernet.Fernet` with a `DISCORD_TOKEN_KEY` env var.

### 3. Create `backend/src/discord_roles.py`

New module with three functions:

**a) `compute_metadata(user: User) -> dict`**

Maps User.roles to the 5 metadata fields:

```python
def compute_metadata(user: User) -> dict:
    roles = set(user.roles)
    admin_level = 3 if Role.IC in roles else 2 if Role.NC in roles else 1 if Role.PRINCE in roles else 0
    judge_level = 3 if Role.RULEMONGER in roles else 2 if Role.JUDGE in roles else 1 if Role.JUDGEKIN in roles else 0
    pt_level = 2 if Role.PTC in roles else 1 if Role.PT in roles else 0
    return {
        "admin_level": admin_level,
        "judge_level": judge_level,
        "pt_level": pt_level,
        "is_member": user.vekn_id is not None,
        "member_since": user.coopted_at.isoformat() if user.coopted_at else "",
    }
```

**b) `push_metadata(user: User, auth_method: AuthMethod) -> bool`**

1. Decrypt refresh token from AuthMethod
2. Exchange refresh token → access token via `POST /oauth2/token` (grant_type=refresh_token)
3. Store new refresh token back on AuthMethod
4. `PUT /users/@me/applications/{app_id}/role-connection` with computed metadata
5. Return success/failure

```
PUT https://discord.com/api/v10/users/@me/applications/{app_id}/role-connection
Authorization: Bearer <user_access_token>
Body: {
    "platform_name": "Archon",
    "platform_username": user.name or user.vekn_id,
    "metadata": { ...computed_metadata }
}
```

**c) `register_metadata() -> bool`**

One-time setup (run as CLI command or on startup):

```
PUT https://discord.com/api/v10/applications/{app_id}/role-connections/metadata
Authorization: Bot <bot_token>
Body: [
    {"key": "admin_level", "name": "Admin Level", "description": "VEKN admin hierarchy (Prince/NC/IC)", "type": 3},
    {"key": "judge_level", "name": "Judge Level", "description": "VEKN judge certification", "type": 3},
    {"key": "pt_level", "name": "Playtest Level", "description": "VEKN playtest role", "type": 3},
    {"key": "is_member", "name": "VEKN Member", "description": "Verified VEKN member", "type": 7},
    {"key": "member_since", "name": "Member Since", "description": "VEKN membership date", "type": 8}
]
```

Type values: 3 = INTEGER_GREATER_THAN_OR_EQUAL, 7 = BOOLEAN_EQUAL, 8 = DATETIME_LESS_THAN_OR_EQUAL.

### 4. Trigger metadata push on role changes

Find all places where `User.roles` or `User.vekn_id` are modified and call `push_metadata`. Key locations:

- `backend/src/routes/admin.py` — role grant/revoke endpoints
- `backend/src/routes/users.py` — if vekn_id is set/changed
- `backend/src/vekn_sync.py` — if roles change during VEKN sync

The push should be **fire-and-forget** (background task via `asyncio.create_task`) so it doesn't block the main request.

### 5. Periodic token refresh

Discord OAuth tokens expire. Add a background task (in `backend/src/main.py` lifespan or a separate cron):

- Query all Discord AuthMethods with `discord_refresh_token is not None`
- For tokens expiring within 24h, refresh and re-push metadata
- Handle revoked tokens gracefully (clear stored token, log warning)

### 6. Discord Developer Portal config

Manual step: set `role_connections_verification_url` in Discord Developer Portal → points to `{API_BASE_URL}/auth/discord/authorize?link=true`

### 7. Environment variables

```
DISCORD_CLIENTID=...          # existing
DISCORD_SECRET=...            # existing
DISCORD_REDIRECT_URI=...      # existing
DISCORD_BOT_TOKEN=...         # new: for metadata registration
DISCORD_TOKEN_KEY=...         # new: Fernet key for encrypting refresh tokens
```

## Discord API Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `PUT /applications/{app.id}/role-connections/metadata` | Bot token | Register schema (one-time) |
| `PUT /users/@me/applications/{app.id}/role-connection` | User OAuth token | Push per-user metadata |
| `POST /oauth2/token` | Client credentials | Token exchange & refresh |

## Alternatives Explored (not pursuing)

- **Discord Social SDK**: Native C++ for games only, no web/HTML5. Can't compile to WASM.
- **Embedded App SDK**: Embeds web apps *inside* Discord (opposite direction). Separate concern for a future Discord bot.
- **Bot direct role assignment**: Per-server install, doesn't scale. Covered by the separate Discord bot project.
- **Webhooks for announcements**: Simple (`POST` JSON to a URL), but separate from Linked Roles. Could be added to tournament config later.

## References

- [Linked Roles tutorial](https://docs.discord.com/developers/tutorials/configuring-app-metadata-for-linked-roles)
- [Role Connection Metadata API](https://discord.com/developers/docs/resources/application-role-connection-metadata)
- [Discord OAuth2 docs](https://docs.discord.com/developers/topics/oauth2)
- [Sample linked-roles repo](https://github.com/discord/linked-roles-sample)
