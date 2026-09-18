"""The process-wide outbound HTTP session."""

import aiohttp

_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=10, sock_read=15)

_session: aiohttp.ClientSession | None = None


def session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=_TIMEOUT, cookie_jar=aiohttp.DummyCookieJar()
        )
    return _session


async def close() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()
    _session = None
