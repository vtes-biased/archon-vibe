import os

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

ARCHON_URL = os.environ.get("ARCHON_URL", "http://localhost:8000")
ARCHON_FRONTEND_URL = os.environ.get("ARCHON_FRONTEND_URL", "http://localhost:5173")

OAUTH_CLIENT_ID = os.environ["OAUTH_CLIENT_ID"]
OAUTH_CLIENT_SECRET = os.environ["OAUTH_CLIENT_SECRET"]
OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI", "http://localhost:9000/oauth/callback"
)

CALLBACK_HOST = os.environ.get("CALLBACK_HOST", "0.0.0.0")
CALLBACK_PORT = int(os.environ.get("CALLBACK_PORT", "9000"))

TOKEN_DB_PATH = os.environ.get("TOKEN_DB_PATH", "bot_tokens.db")

# The bot never knows who holds this: /oauth/userinfo answers that, so /sanction
# carries no local check and just surfaces the API's refusal.
SETUP_CAPABILITY = "create_tournament"


def event_url(obj: dict, tournament_uid: str) -> str:
    """Outward link to an event. The uid form stays valid forever, so the
    fallback for a code not yet stamped is never a wait."""
    code = obj.get("event_code")
    if code:
        return f"{ARCHON_FRONTEND_URL}/t/{code}"
    return f"{ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
