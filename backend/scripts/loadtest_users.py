"""Create throwaway members for loadtest_stream.py and mint their stream tokens.

Runs from the dev repo or inside a deployed wheel's venv (the box), so the
JWT secret is only ever read where it already lives:

    python loadtest_users.py mint --count 200 --ttl-minutes 120 --out tokens.txt
    python loadtest_users.py cleanup

Users are named "Load Test NNN" with no VEKN id, no roles and no contact;
cleanup soft-deletes every non-deleted user carrying that name prefix.
"""

import argparse
import asyncio
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid7

try:
    from backend.src import db
    from backend.src.jwt_config import JWT_ALGORITHM, JWT_SECRET
    from backend.src.models import User
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src import db
    from src.jwt_config import JWT_ALGORITHM, JWT_SECRET
    from src.models import User

import jwt

NAME_PREFIX = "Load Test "


async def mint(count: int, ttl_minutes: int, out: str) -> None:
    await db.init_db()
    now = datetime.now(UTC)
    lines = []
    # 8-digit 99xxxNNN vekn_id: base_data_level needs one for member level, real
    # ids are 7 digits, and the random block dodges the tombstones a previous
    # run's cleanup left reserving their numbers (vekn_id unique index).
    run = secrets.randbelow(1000)
    for i in range(count):
        user = User(
            uid=str(uuid7()),
            modified=now,
            name=f"{NAME_PREFIX}{i:03d}",
            vekn_id=f"99{run:03d}{i:03d}",
        )
        await db.save_user(user)
        token = jwt.encode(
            {
                "sub": user.uid,
                "type": "access",
                "exp": now + timedelta(minutes=ttl_minutes),
                "iat": now,
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )
        lines.append(token)
    Path(out).write_text("\n".join(lines) + "\n")
    await db.close_db()
    print(f"{count} users created, tokens ({ttl_minutes}min) in {out}")


async def cleanup() -> None:
    await db.init_db()
    async with db.get_connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT uid FROM objects WHERE type = 'user' "
                "AND \"full\"->>'name' LIKE %s AND deleted_at IS NULL",
                (NAME_PREFIX + "%",),
            )
        ).fetchall()
    for (uid,) in rows:
        await db.soft_delete_user(uid)
    await db.close_db()
    print(f"{len(rows)} load-test users soft-deleted")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_mint = sub.add_parser("mint")
    p_mint.add_argument("--count", type=int, default=200)
    p_mint.add_argument("--ttl-minutes", type=int, default=120)
    p_mint.add_argument("--out", default="tokens.txt")
    sub.add_parser("cleanup")
    args = parser.parse_args()
    if args.cmd == "mint":
        asyncio.run(mint(args.count, args.ttl_minutes, args.out))
    else:
        asyncio.run(cleanup())


if __name__ == "__main__":
    main()
