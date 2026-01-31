# VEKN Member Synchronization

This system automatically syncs VEKN member data from the official VEKN API into your local database.

## Setup

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Configure your VEKN API credentials in `.env`:**
   ```env
   VEKN_API_BASE_URL=https://www.vekn.net/api
   VEKN_API_USERNAME=your_vekn_username
   VEKN_API_PASSWORD=your_vekn_password
   
   # Enable automatic sync
   VEKN_SYNC_ENABLED=true
   
   # Sync every 6 hours (adjust as needed)
   VEKN_SYNC_INTERVAL_HOURS=6
   ```

3. **Install dependencies:**
   ```bash
   uv sync
   ```

## How It Works

### Automatic Sync
- When enabled, the backend automatically syncs VEKN members on startup and then periodically based on `VEKN_SYNC_INTERVAL_HOURS`
- New members are created automatically
- Existing members are updated with fresh VEKN data

### Local Modification Protection
The sync system **preserves local changes**. When you manually edit a user field via the API, that field is marked as "locally modified" and won't be overwritten by future syncs.

#### User Model Fields:
- `vekn_synced`: `true` if the user was synced from VEKN API
- `vekn_synced_at`: Timestamp of last successful sync
- `local_modifications`: Set of field names that have been manually modified (protected from sync)

#### Example:
1. User "John Doe" is synced from VEKN with city = "Paris"
2. You manually update city to "Lyon" via PUT `/users/{uid}`
3. The `city` field is added to `local_modifications`
4. Future syncs will update other fields but NOT the city

### Manual Sync Trigger

You can manually trigger a sync via the admin endpoint:

```bash
POST /admin/sync-vekn
```

Response:
```json
{
  "status": "success",
  "stats": {
    "created": 150,
    "updated": 50,
    "errors": 0,
    "total": 200
  }
}
```

## Architecture

### Files Created:
- `backend/src/vekn_api.py` - VEKN API client (authentication, fetching members)
- `backend/src/vekn_sync.py` - Sync service (creates/updates users, protects local changes)
- `backend/src/routes/admin.py` - Admin endpoints (manual sync trigger)
- `.env.example` - Environment configuration template

### Files Modified:
- `backend/src/models.py` - Added sync tracking fields to User model
- `backend/src/main.py` - Added background scheduler for periodic sync
- `backend/src/routes/users.py` - Updated to track local modifications
- `frontend/src/types.ts` - Updated TypeScript types
- `pyproject.toml` - Added dependencies (httpx, python-dotenv, apscheduler)

## VEKN API Details

The VEKN API endpoints used:
- `POST /api/login` - Authenticate and get auth token
- `GET /api/registry?filter={query}` - Search for players

### Response Structure:
**IMPORTANT**: All VEKN API responses nest the actual data inside a `data` field:
```json
{
  "err_msg": "",
  "err_code": "",
  "response_id": "...",
  "api": "vekn.login",
  "data": {
    "code": "200",
    "auth": "token_here",
    ...
  }
}
```
Always access `response.data.field` not `response.field`.

### Data Mapping:
| VEKN Field | User Field |
|------------|------------|
| veknid | vekn_id |
| firstname + lastname | name |
| countrycode | country |
| city | city |
| statename | state |

## Disabling Sync

To disable automatic sync, set in `.env`:
```env
VEKN_SYNC_ENABLED=false
```

The backend will start normally without initializing the sync service.

