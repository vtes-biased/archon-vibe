"""Backfill NC/Prince contact emails onto existing users.

The recurring path is vekn_sync, which injects contact_email from
src/data/officials_contacts.json during member sync. This script applies the
same data to users that already exist, so officials become reachable in the
Community → Officials Directory immediately, without waiting for (or paying the
cost of) a full VEKN member re-sync.

Idempotent. Never overwrites a user-edited address (contact_email listed in
local_modifications). save_user recomputes the access projections, so SSE
delivers the new public/member contact_email to clients.

Run from repo root:
    DATABASE_URL=postgresql://archon:archon_dev_password@localhost:5433/archon \
        uv run python backend/scripts/backfill_officials_contacts.py
"""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src.db import decode_json, get_connection, init_db, save_user  # noqa: E402
from src.models import ObjectType, User  # noqa: E402

CONTACTS_PATH = backend_dir / "src" / "data" / "officials_contacts.json"


async def _get_user_by_vekn_id(vekn_id: str) -> User | None:
    async with get_connection() as conn:
        result = await conn.execute(
            'SELECT "full" FROM objects '
            "WHERE type = %s AND \"full\"->>'vekn_id' = %s AND deleted_at IS NULL "
            "LIMIT 1",
            (ObjectType.USER, vekn_id),
        )
        row = await result.fetchone()
        return decode_json(row[0], User) if row else None


async def main() -> None:
    await init_db()
    entries = json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))

    stats = {"updated": 0, "unchanged": 0, "missing_user": 0, "skipped_local": 0}
    for e in entries:
        vekn_id, email = e.get("vekn_id"), e.get("email")
        if not vekn_id or not email:
            continue
        user = await _get_user_by_vekn_id(vekn_id)
        if user is None:
            stats["missing_user"] += 1
            continue
        if "contact_email" in user.local_modifications:
            stats["skipped_local"] += 1
            continue
        if user.contact_email == email:
            stats["unchanged"] += 1
            continue
        user.contact_email = email
        user.modified = datetime.now(UTC)
        await save_user(user)
        stats["updated"] += 1

    print(json.dumps({"total": len(entries), **stats}))


if __name__ == "__main__":
    asyncio.run(main())
