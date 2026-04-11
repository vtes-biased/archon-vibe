"""Bot configuration from environment variables."""

import os

# Discord
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

# Archon backend
ARCHON_URL = os.environ.get("ARCHON_URL", "http://localhost:8000")
ARCHON_FRONTEND_URL = os.environ.get("ARCHON_FRONTEND_URL", "http://localhost:5173")

# OAuth client credentials (registered via POST /oauth/clients)
OAUTH_CLIENT_ID = os.environ["OAUTH_CLIENT_ID"]
OAUTH_CLIENT_SECRET = os.environ["OAUTH_CLIENT_SECRET"]
OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI", "http://localhost:9000/oauth/callback"
)

# Bot HTTP callback server
CALLBACK_HOST = os.environ.get("CALLBACK_HOST", "0.0.0.0")
CALLBACK_PORT = int(os.environ.get("CALLBACK_PORT", "9000"))

# SQLite token store path
TOKEN_DB_PATH = os.environ.get("TOKEN_DB_PATH", "bot_tokens.db")

# Role sets for permission checks
# Setup/teardown/announce — tournament management
SETUP_ROLES = {"IC", "NC", "Prince"}
# Sanctions — includes Ethics committee
SANCTION_ROLES = {"IC", "NC", "Prince", "Ethics"}
