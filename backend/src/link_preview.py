"""Read the title of a member-supplied URL, once, to seed a community-link label.

The only place the server fetches an address a user typed, so every guard against
pointing it at our own network lives here.
"""

import asyncio
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import aiohttp

MAX_REDIRECTS = 3
MAX_BYTES = 64 * 1024
TIMEOUT_S = 5.0
MAX_TITLE = 200


class LinkPreviewError(Exception):
    pass


class _TitleParser(HTMLParser):
    """First `og:title`, else the first `<title>`. Stops at `</head>`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.og_title: str | None = None
        self.title: str | None = None
        self._in_title = False
        self.done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
            return
        if tag != "meta" or self.og_title:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if a.get("property", "").lower() == "og:title":
            self.og_title = a.get("content", "").strip() or None

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data: str) -> None:
        if self._in_title and not self.title:
            self.title = data.strip() or None

    def best(self) -> str | None:
        return (self.og_title or self.title or "")[:MAX_TITLE] or None


async def _checked_url(url: str) -> str:
    """Reject anything that is not a public http(s) address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise LinkPreviewError("Only http and https addresses can be read")
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except socket.gaierror as e:
        raise LinkPreviewError(f"Cannot resolve {parsed.hostname}") from e
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_multicast:
            raise LinkPreviewError("That address is not reachable from the internet")
    return url


async def fetch_link_title(url: str) -> str | None:
    """Follow up to ``MAX_REDIRECTS`` hops, validating each, and read the title
    out of the first 64 KB. Returns ``None`` when the page declares none."""
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_S),
            headers={"User-Agent": "ArchonBot/1.0 (+https://archon.vekn.net)"},
        ) as session:
            for _ in range(MAX_REDIRECTS + 1):
                async with session.get(
                    await _checked_url(url), allow_redirects=False
                ) as response:
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise LinkPreviewError("Redirect without a destination")
                        url = urljoin(url, location)
                        continue
                    if response.status >= 400:
                        raise LinkPreviewError(f"The page answered {response.status}")
                    parser = _TitleParser()
                    async for chunk in response.content.iter_chunked(8192):
                        parser.feed(chunk.decode("utf-8", errors="replace"))
                        if parser.done or response.content.total_bytes > MAX_BYTES:
                            break
                    return parser.best()
    except (aiohttp.ClientError, TimeoutError, UnicodeError, ValueError) as e:
        raise LinkPreviewError(f"Could not read that page: {e}") from e
    raise LinkPreviewError("Too many redirects")
