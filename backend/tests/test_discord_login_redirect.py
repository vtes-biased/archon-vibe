"""A same-origin `?redirect=` path survives the Discord OAuth authorize →
callback round-trip; anything else is dropped at the ingress, never echoed."""

import contextlib
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from aiohttp import web
from src import db

CONSENT_PATH = "/consent?client_id=abc&state=opaque&code_challenge=xyz"


@contextlib.asynccontextmanager
async def fake_discord(monkeypatch, discord_id: str):
    async def token(request: web.Request) -> web.Response:
        return web.json_response(
            {"access_token": "fake-access", "token_type": "Bearer"}
        )

    async def me(request: web.Request) -> web.Response:
        return web.json_response(
            {"id": discord_id, "username": "redirect-tester", "verified": False}
        )

    app = web.Application()
    app.router.add_post("/api/oauth2/token", token)
    app.router.add_get("/api/users/@me", me)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    host, port = runner.addresses[0][:2]
    monkeypatch.setenv("DISCORD_API_BASE", f"http://{host}:{port}/api")
    monkeypatch.setenv("DISCORD_CLIENTID", "test-client-id")
    monkeypatch.setenv("DISCORD_SECRET", "test-secret")
    try:
        yield
    finally:
        await runner.cleanup()


async def _roundtrip(test_client, redirect: str) -> dict:
    resp = await test_client.get(
        "/auth/discord/authorize", params={"redirect": redirect}
    )
    assert resp.status_code == 302
    state = parse_qs(urlparse(resp.headers["Location"]).query)["state"][0]
    resp = await test_client.get(
        "/auth/discord/callback", params={"code": "fake-code", "state": state}
    )
    assert resp.status_code == 302
    location = urlparse(resp.headers["Location"])
    assert location.path == "/login"
    return parse_qs(location.query)


async def _cleanup_auth_method(discord_id: str) -> None:
    auth = await db.get_auth_method_by_identifier("discord", discord_id)
    assert auth is not None
    await db.delete_auth_method(auth.uid)


@pytest.mark.asyncio
async def test_redirect_survives_discord_roundtrip(test_client, monkeypatch):
    discord_id = str(uuid4())
    async with fake_discord(monkeypatch, discord_id):
        query = await _roundtrip(test_client, CONSENT_PATH)
    assert "token" in query and "refresh" in query
    assert query["redirect"] == [CONSENT_PATH]
    await _cleanup_auth_method(discord_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("evil", ["https://evil.com/consent", "//evil.com"])
async def test_non_path_redirect_is_dropped(test_client, monkeypatch, evil):
    discord_id = str(uuid4())
    async with fake_discord(monkeypatch, discord_id):
        query = await _roundtrip(test_client, evil)
    assert "redirect" not in query
    await _cleanup_auth_method(discord_id)
