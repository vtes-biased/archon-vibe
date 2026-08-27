import os

import aiosqlite

from . import config


class TokenStore:
    def __init__(self, db_path: str = config.TOKEN_DB_PATH):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        # systemd UMask=0077 covers the SQLite sidecar files; this best-effort
        # chmod also hardens dev/non-systemd runs. No-op for ":memory:".
        try:
            os.chmod(self._db_path, 0o600)
        except OSError:
            pass
        # Pre-scope rows are unscoped grants the backend now refuses outright, and
        # a primary key is not ALTERable: drop, and let /setup and /register
        # re-authorize per event.
        async with self._db.execute("PRAGMA table_info(tokens)") as cur:
            columns = {row[1] async for row in cur}
        if columns and "tournament_uid" not in columns:
            await self._db.execute("DROP TABLE tokens")
            await self._db.execute("DROP TABLE IF EXISTS pending_oauth")

        # A grant is per (user, event): the backend issues no token that reaches
        # more than one tournament, so neither does the store.
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                discord_id TEXT NOT NULL,
                tournament_uid TEXT NOT NULL,
                archon_uid TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                PRIMARY KEY (discord_id, tournament_uid)
            )
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tokens_archon_uid ON tokens(archon_uid)"
        )
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS guild_tournaments (
                guild_id TEXT NOT NULL,
                tournament_uid TEXT NOT NULL,
                organizer_discord_id TEXT NOT NULL,
                announcement_channel_id TEXT,
                lobby_channel_id TEXT,
                judges_channel_id TEXT,
                category_id TEXT,
                PRIMARY KEY (guild_id, tournament_uid)
            )
        """)
        # Migration: the Discord scheduled-event id for this tournament (added later).
        # ALTER on an existing table; ignore the duplicate-column error on re-run.
        try:
            await self._db.execute(
                "ALTER TABLE guild_tournaments ADD COLUMN scheduled_event_id TEXT"
            )
        except aiosqlite.OperationalError:
            pass
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS pending_oauth (
                state TEXT PRIMARY KEY,
                discord_id TEXT NOT NULL,
                tournament_uid TEXT NOT NULL,
                code_verifier TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Needs SQLite >= 3.35 (2021): older swallows "unsupported" here and the
        # leftover NOT NULL columns make the next INSERT fail loudly.
        for col in ("action", "extra", "guild_id", "channel_id"):
            try:
                await self._db.execute(f"ALTER TABLE pending_oauth DROP COLUMN {col}")
            except aiosqlite.OperationalError:
                pass
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def get_tokens(self, discord_id: str, tournament_uid: str) -> dict | None:
        assert self._db
        async with self._db.execute(
            "SELECT archon_uid, access_token, refresh_token FROM tokens "
            "WHERE discord_id = ? AND tournament_uid = ?",
            (discord_id, tournament_uid),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "archon_uid": row[0],
                "access_token": row[1],
                "refresh_token": row[2],
            }

    async def store_tokens(
        self,
        discord_id: str,
        tournament_uid: str,
        archon_uid: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        assert self._db
        await self._db.execute(
            """INSERT INTO tokens
               (discord_id, tournament_uid, archon_uid, access_token, refresh_token)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(discord_id, tournament_uid) DO UPDATE SET
                 archon_uid = excluded.archon_uid,
                 access_token = excluded.access_token,
                 refresh_token = excluded.refresh_token""",
            (discord_id, tournament_uid, archon_uid, access_token, refresh_token),
        )
        await self._db.commit()

    async def get_discord_id_by_archon_uid(self, archon_uid: str) -> str | None:
        assert self._db
        async with self._db.execute(
            "SELECT discord_id FROM tokens WHERE archon_uid = ?",
            (archon_uid,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    async def get_discord_ids_by_archon_uids(
        self, archon_uids: list[str]
    ) -> dict[str, str]:
        assert self._db
        if not archon_uids:
            return {}
        placeholders = ",".join("?" for _ in archon_uids)
        result = {}
        async with self._db.execute(
            f"SELECT archon_uid, discord_id FROM tokens WHERE archon_uid IN ({placeholders})",
            archon_uids,
        ) as cur:
            async for row in cur:
                result[row[0]] = row[1]
        return result

    async def remove_tokens(self, discord_id: str, tournament_uid: str) -> None:
        assert self._db
        await self._db.execute(
            "DELETE FROM tokens WHERE discord_id = ? AND tournament_uid = ?",
            (discord_id, tournament_uid),
        )
        await self._db.commit()

    async def link_tournament(
        self,
        guild_id: str,
        tournament_uid: str,
        organizer_discord_id: str,
        announcement_channel_id: str,
        lobby_channel_id: str,
        judges_channel_id: str,
        category_id: str,
    ) -> None:
        assert self._db
        await self._db.execute(
            """INSERT INTO guild_tournaments
               (guild_id, tournament_uid, organizer_discord_id,
                announcement_channel_id, lobby_channel_id, judges_channel_id, category_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, tournament_uid) DO UPDATE SET
                 organizer_discord_id = excluded.organizer_discord_id,
                 announcement_channel_id = excluded.announcement_channel_id,
                 lobby_channel_id = excluded.lobby_channel_id,
                 judges_channel_id = excluded.judges_channel_id,
                 category_id = excluded.category_id""",
            (
                guild_id,
                tournament_uid,
                organizer_discord_id,
                announcement_channel_id,
                lobby_channel_id,
                judges_channel_id,
                category_id,
            ),
        )
        await self._db.commit()

    async def get_tournament_link(
        self, guild_id: str, tournament_uid: str
    ) -> dict | None:
        assert self._db
        async with self._db.execute(
            """SELECT organizer_discord_id, announcement_channel_id, lobby_channel_id,
                      judges_channel_id, category_id, scheduled_event_id
               FROM guild_tournaments WHERE guild_id = ? AND tournament_uid = ?""",
            (guild_id, tournament_uid),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "organizer_discord_id": row[0],
                "announcement_channel_id": row[1],
                "lobby_channel_id": row[2],
                "judges_channel_id": row[3],
                "category_id": row[4],
                "scheduled_event_id": row[5],
            }

    async def set_scheduled_event_id(
        self, guild_id: str, tournament_uid: str, event_id: str | None
    ) -> None:
        assert self._db
        await self._db.execute(
            """UPDATE guild_tournaments SET scheduled_event_id = ?
               WHERE guild_id = ? AND tournament_uid = ?""",
            (event_id, guild_id, tournament_uid),
        )
        await self._db.commit()

    async def get_guild_tournaments(self, guild_id: str) -> list[dict]:
        assert self._db
        rows = []
        async with self._db.execute(
            "SELECT tournament_uid, organizer_discord_id, category_id FROM guild_tournaments WHERE guild_id = ?",
            (guild_id,),
        ) as cur:
            async for row in cur:
                rows.append(
                    {
                        "tournament_uid": row[0],
                        "organizer_discord_id": row[1],
                        "category_id": row[2],
                    }
                )
        return rows

    async def get_tournament_by_category(
        self, guild_id: str, category_id: str
    ) -> dict | None:
        assert self._db
        async with self._db.execute(
            """SELECT tournament_uid, organizer_discord_id, category_id,
                      announcement_channel_id, lobby_channel_id, judges_channel_id
               FROM guild_tournaments WHERE guild_id = ? AND category_id = ?""",
            (guild_id, category_id),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "tournament_uid": row[0],
                "organizer_discord_id": row[1],
                "category_id": row[2],
                "announcement_channel_id": row[3],
                "lobby_channel_id": row[4],
                "judges_channel_id": row[5],
            }

    async def get_all_guild_tournaments(self) -> list[dict]:
        assert self._db
        rows = []
        async with self._db.execute(
            "SELECT guild_id, tournament_uid, organizer_discord_id FROM guild_tournaments",
        ) as cur:
            async for row in cur:
                rows.append(
                    {
                        "guild_id": row[0],
                        "tournament_uid": row[1],
                        "organizer_discord_id": row[2],
                    }
                )
        return rows

    async def unlink_tournament(self, guild_id: str, tournament_uid: str) -> None:
        assert self._db
        await self._db.execute(
            "DELETE FROM guild_tournaments WHERE guild_id = ? AND tournament_uid = ?",
            (guild_id, tournament_uid),
        )
        await self._db.commit()

    async def store_pending_oauth(
        self,
        state: str,
        discord_id: str,
        tournament_uid: str,
        code_verifier: str,
    ) -> None:
        assert self._db
        await self._db.execute(
            """INSERT INTO pending_oauth
               (state, discord_id, tournament_uid, code_verifier)
               VALUES (?, ?, ?, ?)""",
            (state, discord_id, tournament_uid, code_verifier),
        )
        await self._db.commit()

    async def get_pending_oauth(self, state: str) -> dict | None:
        assert self._db
        # Commit immediately: without it the DELETE's implicit write transaction
        # dangles on the shared connection and is lost entirely on crash.
        await self._db.execute(
            "DELETE FROM pending_oauth WHERE created_at < datetime('now', '-15 minutes')"
        )
        await self._db.commit()
        async with self._db.execute(
            "SELECT discord_id, tournament_uid, code_verifier FROM pending_oauth "
            "WHERE state = ?",
            (state,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "discord_id": row[0],
                "tournament_uid": row[1],
                "code_verifier": row[2],
            }

    async def remove_pending_oauth(self, state: str) -> None:
        assert self._db
        await self._db.execute("DELETE FROM pending_oauth WHERE state = ?", (state,))
        await self._db.commit()
