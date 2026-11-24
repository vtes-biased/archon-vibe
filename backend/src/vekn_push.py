import logging
import os
from datetime import UTC, datetime

from .broadcast import broadcast_precomputed
from .db import (
    batch_read_connection,
    decode_json,
    get_user_by_uid,
    save_user,
)
from .geonames import get_country
from .models import ObjectType, User
from .vekn_api import (
    VEKNAPIClient,
    VEKNAPIConnectionError,
    VEKNAPIError,
)

logger = logging.getLogger(__name__)


# deploy/grafana.py parses this line shape into its failing-members table.
def _member_failed(user: User, reason: str, *, exc_info: bool = False) -> None:
    logger.error(
        f"VEKN push failed: member={user.vekn_id} reason={reason}", exc_info=exc_info
    )


def vekn_push_client() -> VEKNAPIClient | None:
    """A VEKNAPIClient when VEKN_PUSH is enabled, else None."""
    if os.getenv("VEKN_PUSH", "").lower() != "true":
        return None
    return VEKNAPIClient()


async def push_member(
    client: VEKNAPIClient,
    user: User,
) -> bool:
    """Push a locally-created member to VEKN registry. Returns True on success."""
    if not os.getenv("VEKN_PUSH", "").lower() == "true":
        return False

    if not user.vekn_id:
        return False

    name_parts = (user.name or "").split(maxsplit=1)
    firstname = name_parts[0] if name_parts else "Unknown"
    lastname = name_parts[1] if len(name_parts) > 1 else "Unknown"

    email = user.contact_email or f"{user.vekn_id}@placeholder.vekn.net"
    country = user.country or ""

    # The registry refuses a create with an empty city.
    country_data = get_country(country) if country else None
    city = user.city or (country_data["capital"] if country_data else "")

    try:
        await client.create_member(
            veknid=user.vekn_id,
            firstname=firstname,
            lastname=lastname,
            email=email,
            country=country,
            state=user.state or "",
            city=city,
        )
    except VEKNAPIConnectionError:
        raise  # batch-fatal: let batch_push abort and retry next cycle
    except VEKNAPIError as e:
        _member_failed(user, str(e))
        return False

    # Re-fetch — batch_push may have loaded this user minutes ago; write only
    # the vekn-sync flags so interim profile edits aren't clobbered.
    fresh = await get_user_by_uid(user.uid) or user
    fresh.vekn_synced = True
    fresh.vekn_synced_at = datetime.now(UTC)
    fresh.modified = datetime.now(UTC)
    bd = await save_user(fresh)
    broadcast_precomputed(bd)
    logger.info(f"Member {user.vekn_id} pushed to VEKN")
    return True


async def push_member_background(user: User) -> None:
    """push_member with its own client and swallowed errors, for asyncio.create_task.

    Failures are log-only — vekn_synced stays false, so batch_push retries hourly.
    """
    try:
        client = vekn_push_client()
        if client is not None:
            await push_member(client, user)
    except Exception:
        logger.exception(f"Failed to push member {user.vekn_id} to VEKN")


async def batch_push(client: VEKNAPIClient) -> dict:
    """Push all unsynced members. Fail-fast on VEKNAPIConnectionError so an
    outage aborts the batch; per-item data errors skip just that member."""
    stats = {
        "members_pushed": 0,
        "errors": 0,
        "aborted": False,
    }

    if not os.getenv("VEKN_PUSH", "").lower() == "true":
        return stats

    try:
        async with batch_read_connection() as conn:
            result = await conn.execute(
                """
                SELECT "full" FROM objects
                WHERE type = %s
                  AND "full"->>'vekn_id' IS NOT NULL
                  AND ("full"->>'vekn_synced')::boolean = false
                """,
                (ObjectType.USER,),
            )
            rows = await result.fetchall()

        for row in rows:
            u = decode_json(row[0], User)
            if u.anonymized_at:
                continue
            try:
                if await push_member(client, u):
                    stats["members_pushed"] += 1
                else:
                    stats["errors"] += 1
            except VEKNAPIConnectionError:
                raise
            except Exception:
                _member_failed(u, "crash", exc_info=True)
                stats["errors"] += 1
    except VEKNAPIConnectionError as e:
        logger.warning(
            f"Batch push aborted — VEKN unreachable: {e}; retries next cycle"
        )
        stats["aborted"] = True

    logger.info(f"Batch push complete: {stats}")
    return stats
