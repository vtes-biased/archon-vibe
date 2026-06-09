"""Shared loader for the generated VtesCard database (``cards.json``).

``cards.json`` is produced by ``scripts/update_cards.py`` (``just cards``) into the
engine build dir. The backend reads it to serve ``/api/cards`` and to validate
decklists server-side. Resolution order is chosen so the same code works in dev,
in a wheel deploy, and with a deploy-managed path — independent of the wheel
packaging layout:

1. ``CARDS_JSON_PATH`` env var — a deploy can point this at the shipped file
   (e.g. a CI release artifact placed by ansible);
2. package data — ``cards.json`` bundled into this package's ``data/`` (e.g. via
   a hatch ``force-include`` of ``engine/data/cards.json``), located by anchoring
   on this module's own package so it resolves whatever the package is named;
3. dev fallback — ``<repo>/engine/data/cards.json``, the ``just cards`` output.

Returns ``None`` when unavailable so callers can 503; the result is cached only on
success, so a server started before ``cards.json`` exists picks it up on retry.
"""

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
    """Raw ``cards.json`` bytes, or ``None`` if unavailable (callers should 503)."""
    global _cards_bytes
    if _cards_bytes is None:
        _cards_bytes = _read_cards()
    return _cards_bytes


def cards_json_text() -> str | None:
    """``cards.json`` as UTF-8 text, or ``None`` if unavailable."""
    data = cards_json_bytes()
    return data.decode("utf-8") if data is not None else None
