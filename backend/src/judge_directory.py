"""Judge and Sheriff from the VTES Exams public judge directory."""

import logging
from datetime import UTC, datetime

import msgspec

from . import http_client
from .accounts import save_member
from .broadcast import broadcast_precomputed
from .db import batch_read_connection, decode_json
from .models import Role, User

logger = logging.getLogger(__name__)

DIRECTORY_URL = "https://www.vtesexams.com/api/v1/judges/"

_RANK_ROLES = {"Elder": Role.JUDGE, "Ancilla": Role.SHERIFF, "Neonate": Role.SHERIFF}
_DIRECTORY_ROLES = {Role.JUDGE, Role.SHERIFF}


class JudgeEntry(msgspec.Struct):
    vekn: str
    rank: str
    valid_until: str


_etag: str | None = None
_entries: list[JudgeEntry] = []


async def _fetch_directory() -> list[JudgeEntry]:
    """A 304 still reconciles from the cached body: our side moves while the
    directory sits still — validity dates pass, members gain a VEKN id."""
    global _etag, _entries
    headers = {"If-None-Match": _etag} if _etag and _entries else {}
    async with http_client.session().get(DIRECTORY_URL, headers=headers) as resp:
        if resp.status == 304:
            return _entries
        resp.raise_for_status()
        entries = msgspec.json.decode(await resp.read(), type=list[JudgeEntry])
        _etag, _entries = resp.headers.get("ETag"), entries
        return entries


def _directory_role(entry: JudgeEntry, today: str) -> Role | None:
    if entry.valid_until < today:
        return None
    return _RANK_ROLES.get(entry.rank)


async def _candidates(vekn_ids: list[str]) -> list[User]:
    async with batch_read_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND deleted_at IS NULL
              AND ("full"->>'vekn_id' = ANY(%s)
                   OR "full"->'roles' ?| array['Judge', 'Sheriff'])""",
            (vekn_ids,),
        )
        return [decode_json(row[0], User) for row in await result.fetchall()]


async def sync_judges(*, apply: bool = True) -> dict:
    entries = await _fetch_directory()
    if not entries:
        raise ValueError("judge directory returned no entries — refusing to revoke all")
    today = datetime.now(UTC).date().isoformat()
    wanted: dict[str, Role | None] = {}
    for entry in entries:
        wanted[entry.vekn] = _directory_role(entry, today) or wanted.get(entry.vekn)
    if unknown := {e.rank for e in entries} - _RANK_ROLES.keys():
        logger.warning(
            f"Judge directory: unknown ranks {sorted(unknown)} grant nothing"
        )

    users = await _candidates(list(wanted))
    matched = {u.vekn_id for u in users}
    stats: dict = {
        "listed": len(entries),
        "unmatched": sorted(v for v in wanted if v not in matched),
        "changes": [],
    }
    if stats["unmatched"]:
        logger.warning(
            f"Judge directory: no member holds VEKN ids {stats['unmatched']}"
        )
    now = datetime.now(UTC)
    for user in users:
        role = wanted.get(user.vekn_id or "")
        kept = [r for r in user.roles if r not in _DIRECTORY_ROLES]
        roles = kept + [role] if role else kept
        if set(roles) == set(user.roles):
            continue
        stats["changes"].append(
            {
                "vekn_id": user.vekn_id,
                "name": user.name,
                "before": sorted(r for r in user.roles if r in _DIRECTORY_ROLES),
                "after": [role] if role else [],
            }
        )
        if not apply:
            continue
        before = msgspec.structs.replace(user)
        user.roles = roles
        user.modified = now
        broadcast_precomputed(await save_member(before, user))
    logger.info(
        f"Judge directory: {len(entries)} listed, {len(stats['changes'])} members "
        f"{'changed' if apply else 'would change'}"
    )
    return stats
