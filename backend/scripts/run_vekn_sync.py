"""Standalone VEKN sync runner — member sync then tournament sync.

Used in the migration rehearsal (empty DB → ETL → this) and mirrors the
scheduled `main.run_vekn_sync`. Reads VEKN_API_USERNAME / VEKN_API_PASSWORD from
the environment or the repo-root `.env` file (loaded here), so credentials never
need to be passed on the command line.

    cd backend
    # VEKN_API_USERNAME / VEKN_API_PASSWORD live in the repo-root .env (gitignored)
    DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_new \\
    uv run python scripts/run_vekn_sync.py
"""

import asyncio
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

# Dev convenience: find a .env by walking up from this file (repo-root .env).
# In beta/prod the env vars come from systemd/server environment and no .env
# exists — load_dotenv is then a no-op and os.getenv reads the real env. Same
# pattern as main.py. Does NOT override already-set env vars.
load_dotenv()

from src import db
from src.vekn_sync import VEKNSyncService
from src.vekn_tournament_sync import sync_all_tournaments


async def main() -> None:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("DATABASE_URL required")
    if not (os.getenv("VEKN_API_USERNAME") and os.getenv("VEKN_API_PASSWORD")):
        sys.exit(
            "VEKN_API_USERNAME and VEKN_API_PASSWORD required (env or backend/.env)"
        )

    db.DB_URL = dsn
    await db.init_db()
    svc = VEKNSyncService()
    try:
        print("→ VEKN member sync (fetches ~19k from vekn.net — may take a while)…")
        members = await svc.sync_all_members()
        print(f"  members: {members}")
        print("→ VEKN tournament sync…")
        tournaments = await sync_all_tournaments(svc.client)
        print(f"  tournaments: {tournaments}")
    finally:
        await svc.close()
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
