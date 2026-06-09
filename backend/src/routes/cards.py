"""Cards API endpoint: serve cards.json with ETag caching."""

import hashlib

from fastapi import APIRouter, Request, Response

from ..card_data import cards_json_bytes

router = APIRouter(prefix="/api", tags=["cards"])

_cards_etag: str | None = None


def _load_cards():
    """Return (bytes, etag) for cards.json, or (None, None) if unavailable."""
    global _cards_etag
    data = cards_json_bytes()
    if data is None:
        return None, None
    if _cards_etag is None:
        _cards_etag = hashlib.md5(data).hexdigest()
    return data, _cards_etag


@router.get("/cards")
async def get_cards(request: Request) -> Response:
    """Serve cards.json with ETag caching."""
    data, etag = _load_cards()
    if data is None:
        return Response(status_code=503, content="Cards data not available")

    # Check If-None-Match for caching
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    return Response(
        content=data,
        media_type="application/json",
        headers={"ETag": f'"{etag}"', "Cache-Control": "public, max-age=3600"},
    )
