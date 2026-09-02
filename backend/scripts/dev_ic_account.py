"""Create the fixed dev IC account, so members management can be exercised signed in.

Run via: uv run python backend/scripts/dev_ic_account.py
"""

import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from datetime import UTC, datetime  # noqa: E402
from uuid import uuid7  # noqa: E402

from argon2 import PasswordHasher  # noqa: E402
from src.db import (  # noqa: E402
    DB_URL,
    get_auth_method_by_identifier,
    get_user_by_vekn_id,
    init_db,
    insert_auth_method,
    save_user,
)
from src.models import (  # noqa: E402
    AuthMethod,
    AuthMethodType,
    Role,
    User,
)

DEV_DSN = "postgresql://archon:archon_dev_password@localhost:5433/archon"

EMAIL = "dev-ic@example.com"
PASSWORD = "DevIC!2026"
NAME = "Dev IC"
COUNTRY = "US"
VEKN_ID = "9998001"


async def create() -> str:
    if DB_URL != DEV_DSN:
        raise SystemExit(
            f"Refusing to run: DATABASE_URL is {DB_URL!r}, not the local dev "
            f"database {DEV_DSN!r}. This script writes a checked-in password."
        )

    await init_db()

    if await get_auth_method_by_identifier("email", EMAIL):
        return f"{EMAIL} already present"

    clash = await get_user_by_vekn_id(VEKN_ID)
    if clash:
        raise SystemExit(
            f"Refusing to run: VEKN ID {VEKN_ID} already belongs to {clash.name!r} "
            f"({clash.uid}). This script creates rows, it never takes one over."
        )

    now = datetime.now(UTC)
    user = User(
        uid=str(uuid7()),
        modified=now,
        name=NAME,
        country=COUNTRY,
        vekn_id=VEKN_ID,
        roles=[Role.IC],
        contact_email=EMAIL,
    )
    await save_user(user)

    await insert_auth_method(
        AuthMethod(
            uid=str(uuid7()),
            modified=now,
            user_uid=user.uid,
            method_type=AuthMethodType.EMAIL,
            identifier=EMAIL,
            credential_hash=PasswordHasher().hash(PASSWORD),
            verified=True,
            created_at=now,
            last_used_at=now,
        )
    )
    return f"created {EMAIL} / {PASSWORD} (VEKN {VEKN_ID}, role IC)"


if __name__ == "__main__":
    print(asyncio.run(create()))
