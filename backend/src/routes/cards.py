"""Cards API endpoint: serve cards.json with ETag caching."""

import hashlib
from pathlib import Path

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/api", tags=["cards"])

_cards_data: bytes | None = None
_cards_etag: str | None = None


def _load_cards():
    global _cards_data, _cards_etag
    if _cards_data is None:
        cards_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "engine"
            / "data"
            / "cards.json"
        )
        if not cards_path.exists():
            return None, None
        _cards_data = cards_path.read_bytes()
        _cards_etag = hashlib.md5(_cards_data).hexdigest()
    return _cards_data, _cards_etag


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
