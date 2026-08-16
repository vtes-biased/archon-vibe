"""Regression guard for seating announcements showing raw UUIDs: the bot's
scoped SSE stream carries no user objects otherwise. `_scoped_catchup_frames`
must emit each participant's User object and seed `sent` for the live-refresh
diff.
"""

from datetime import UTC, datetime

import pytest
from src import db
from src.main import _scoped_catchup_frames
from src.models import Player, Tournament, User

from tests.conftest import seed_tournament

NOW = datetime.now(UTC)


@pytest.mark.asyncio
async def test_scoped_catchup_seeds_participant_identities(test_db):
    org = User(uid="org-1", modified=NOW, name="Olivia Organizer")
    p1 = User(uid="play-1", modified=NOW, name="Pat Player", nickname="patzilla")
    p2 = User(uid="play-2", modified=NOW, name="Robin Roe")
    for u in (org, p1, p2):
        await db.save_user(u)

    t = Tournament(
        uid="trn-1",
        modified=NOW,
        name="Cup",
        organizers_uids=["org-1"],
        players=[Player(user_uid="play-1"), Player(user_uid="play-2")],
    )
    await seed_tournament(t)
    try:
        sent: set[str] = set()
        frames, _ts = await _scoped_catchup_frames(org, "trn-1", sent)
        blob = "".join(frames)

        assert '"type":"tournament"' in blob
        assert '"type":"users"' in blob
        # Identities resolvable: name + nickname both present for the bot.
        assert "Pat Player" in blob and "patzilla" in blob
        assert "Robin Roe" in blob
        # Players AND organizers seeded, so the live-refresh diff is primed.
        assert sent == {"org-1", "play-1", "play-2"}

        # A second call with the seeded set adds nothing (no re-send churn).
        more, _ = await _scoped_catchup_frames(org, "trn-1", sent)
        assert not any('"type":"users"' in f for f in more)
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE uid = 'trn-1'")
