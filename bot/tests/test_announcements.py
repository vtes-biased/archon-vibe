"""A regression here is what made seating announcements show raw UUIDs."""

from __future__ import annotations

import unittest

from archon_bot.announcements import player_display

UID = "435f1561-aaaa-bbbb-cccc-ddddeeeeffff"


class PlayerDisplayTest(unittest.TestCase):
    def test_mention_wins_when_linked_and_requested(self):
        out = player_display(
            UID,
            [{"user_uid": UID, "display_name": "Nick"}],
            discord_id_map={UID: 123},
            user_names={UID: {"name": "Real Name", "nickname": "vk"}},
            mention=True,
        )
        self.assertEqual(out, "<@123>")

    def test_no_mention_when_not_requested(self):
        out = player_display(
            UID,
            [{"user_uid": UID, "display_name": "Nick"}],
            discord_id_map={UID: 123},
            mention=False,
        )
        self.assertEqual(out, "Nick")

    def test_tournament_nickname_preferred_over_cached_identity(self):
        out = player_display(
            UID,
            [{"user_uid": UID, "display_name": "Nick"}],
            user_names={UID: {"name": "Real Name", "nickname": "vk"}},
            mention=True,
        )
        self.assertEqual(out, "Nick")

    def test_cached_nickname_then_name(self):
        self.assertEqual(
            player_display(
                UID,
                [{"user_uid": UID}],
                user_names={UID: {"name": "Real", "nickname": "vk"}},
            ),
            "vk",
        )
        self.assertEqual(
            player_display(
                UID,
                [{"user_uid": UID}],
                user_names={UID: {"name": "Real", "nickname": None}},
            ),
            "Real",
        )

    def test_uid_prefix_when_nothing_known(self):
        self.assertEqual(player_display(UID, []), UID[:8])
        self.assertEqual(
            player_display(UID, [{"user_uid": UID}], discord_id_map={}, mention=True),
            UID[:8],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
