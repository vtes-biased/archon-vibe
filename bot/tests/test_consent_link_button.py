"""The consent link ships as a Discord link button, whose URL Discord caps at
512 characters. The values below mirror the production inventory
(`ansible/inventories/prod`), so a domain change updates this test too."""

from __future__ import annotations

import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot import config  # noqa: E402
from archon_bot.oauth_utils import (  # noqa: E402
    consent_button,
    generate_pkce,
    generate_state,
    make_oauth_url,
)

DISCORD_LINK_BUTTON_URL_MAX = 512
TOURNAMENT_UID = "01994a2e-3f5c-7c1e-9a4b-2f1e8d6c5b4a"


def test_consent_url_fits_a_link_button(monkeypatch) -> None:
    monkeypatch.setattr(config, "ARCHON_FRONTEND_URL", "https://archon.vekn.net")
    monkeypatch.setattr(
        config, "OAUTH_REDIRECT_URI", "https://bot.archon.vekn.net/oauth/callback"
    )
    monkeypatch.setattr(config, "OAUTH_CLIENT_ID", "x" * 32)
    _, code_challenge = generate_pkce()
    url = make_oauth_url(generate_state(), code_challenge, TOURNAMENT_UID)
    assert len(url) <= DISCORD_LINK_BUTTON_URL_MAX
    row = consent_button(url, "Authorize Archon Bot")
    (button,) = row.components
    assert button.url == url
