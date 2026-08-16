"""Loader for the generated VtesCard database (``cards.json``), resolved in order:
``CARDS_JSON_PATH`` env override, packaged ``data/``, dev-tree fallback. Returns
``None`` when unavailable; cached only on success, so a server started before the
file exists picks it up on retry."""

import os
from importlib.resources import files
from pathlib import Path

_cards_bytes: bytes | None = None


def _read_cards() -> bytes | None:
    env_path = os.getenv("CARDS_JSON_PATH")
    if env_path:
        p = Path(env_path)
        return p.read_bytes() if p.is_file() else None
    resource = files(__package__).joinpath("data", "cards.json")
    if resource.is_file():
        return resource.read_bytes()
    dev = Path(__file__).resolve().parents[2] / "engine" / "data" / "cards.json"
    return dev.read_bytes() if dev.is_file() else None


def cards_json_bytes() -> bytes | None:
    global _cards_bytes
    if _cards_bytes is None:
        _cards_bytes = _read_cards()
    return _cards_bytes


def cards_json_text() -> str | None:
    data = cards_json_bytes()
    return data.decode("utf-8") if data is not None else None
