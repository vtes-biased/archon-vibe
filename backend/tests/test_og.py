"""Open Graph share-stub render invariant.

`render_og_html` produces HTML served UNAUTHENTICATED to social crawlers (and the
rare human who hits the stub). Two things must hold or the stub is unsafe/wrong:

  1. The tournament name/description are user-controlled and land inside <meta
     content="..."> attributes — they MUST be HTML-escaped, or a name like
     `"><script>` breaks out of the attribute into executable markup (stored XSS
     reachable without login). This is the load-bearing assertion.
  2. The card type + image dimensions track `banner_path`: a banner yields a
     large card at 1200x630, its absence the square 512 fallback icon; a
     soft-deleted (deleted_at) tournament must NOT leak its banner.

`pub` is built via the real `compute_tournament_public` projection so the test
exercises the shipped field contract, not an invented dict.
"""

from datetime import UTC, datetime

import msgspec
from src.access_levels import compute_tournament_public
from src.models import League, Tournament
from src.og import (
    BANNER_H,
    BANNER_W,
    FALLBACK_IMAGE,
    ICON_H,
    ICON_W,
    render_league_og_html,
    render_og_html,
)

BASE = "https://archon.example"


def _pub(**overrides) -> dict:
    """Public projection of a Tournament with the given field overrides.

    Built via the same model→builtins→projection path as the write path in
    db.save_object (msgspec.to_builtins + compute_*), so the test rides the real
    field contract rather than an invented dict.
    """
    fields = {"name": "Paris Open", "country": "France", **overrides}
    t = Tournament(uid="t-uid", modified=datetime.now(UTC), **fields)
    return compute_tournament_public(msgspec.to_builtins(t))


def test_og_escapes_user_content_and_tracks_banner():
    # 1. Attribute-breakout XSS: a hostile name must not escape the meta content attr.
    hostile = '"><script>alert(1)</script>'
    out = render_og_html(BASE, "t-uid", _pub(name=hostile))
    assert hostile not in out  # raw payload never appears verbatim
    assert "<script>" not in out  # no unescaped tag injected
    assert "&lt;script&gt;" in out  # escaped form is what got rendered

    # 2a. With a banner: large card, absolute image URL, 1200x630.
    withb = render_og_html(BASE, "t-uid", _pub(banner_path="/banners/t-uid.png"))
    assert 'name="twitter:card" content="summary_large_image"' in withb
    assert f'content="{BASE}/banners/t-uid.png"' in withb
    assert f'content="{BANNER_W}"' in withb and f'content="{BANNER_H}"' in withb

    # 2b. No banner: summary card with the square fallback icon at 512x512.
    nob = render_og_html(BASE, "t-uid", _pub())
    assert 'name="twitter:card" content="summary"' in nob
    assert f'content="{BASE}{FALLBACK_IMAGE}"' in nob
    assert f'content="{ICON_W}"' in nob and f'content="{ICON_H}"' in nob

    # 2c. Soft-deleted falls back to the site-wide card and must NOT emit the banner.
    deleted = render_og_html(
        BASE,
        "t-uid",
        _pub(banner_path="/banners/t-uid.png", deleted_at=datetime.now(UTC)),
    )
    assert "/banners/t-uid.png" not in deleted
    assert 'name="twitter:card" content="summary"' in deleted

    # None (unknown uid) is the same site-wide fallback, never an error.
    assert 'name="twitter:card" content="summary"' in render_og_html(BASE, "x", None)


def test_league_og_escapes_user_content():
    """Same unauthenticated-render invariants for the league stub: hostile
    name/description must be escaped; unknown/deleted → site-wide card."""
    hostile = '"><script>alert(1)</script>'
    league = League(
        uid="l-uid",
        modified=datetime.now(UTC),
        name=hostile,
        country="FR",
        description="Monthly series",
    )
    pub = msgspec.to_builtins(league)  # leagues project as identity (fully public)
    out = render_league_og_html(BASE, "l-uid", pub, event_count=3)
    assert hostile not in out and "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "3 events" in out and "Monthly series" in out
    assert f'href="{BASE}/leagues/l-uid"' in out
    # Leagues have no banner: always the square summary card.
    assert 'name="twitter:card" content="summary"' in out

    deleted = msgspec.to_builtins(league) | {"deleted_at": datetime.now(UTC)}
    assert hostile not in render_league_og_html(BASE, "l-uid", deleted, 3)
    assert 'content="Archon"' in render_league_og_html(BASE, "x", None)
