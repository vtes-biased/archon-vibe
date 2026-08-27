"""Server-rendered Open Graph stubs for shared tournament and league links.

Pure render, no request/db: the routes in main.py supply the public-level
projection dict, so this stays unit-testable and can't over-expose member fields.
"""

import html
from datetime import datetime

SITE_TITLE = "Archon"
BETA_SITE_TITLE = "Archon Beta"
BETA_HOST = "archon.krcg.org"
SITE_DESCRIPTION = "VEKN Tournament Management - Web App"
FALLBACK_IMAGE = "/icon-512.png"  # square site icon
BETA_FALLBACK_IMAGE = "/icon-512-beta.png"
# Banner is the de-facto universal og:image size.
BANNER_W, BANNER_H = 1200, 630
ICON_W, ICON_H = 512, 512


def _is_beta(base_url: str) -> bool:
    """One deployment serves both hosts, so the environment is the host we were
    reached on — the same resolution the frontend head script makes."""
    return BETA_HOST in base_url


def _site_title(base_url: str) -> str:
    return BETA_SITE_TITLE if _is_beta(base_url) else SITE_TITLE


def _format_date(start: str | None) -> str | None:
    """Date portion of an ISO `start` as e.g. "23 Jun 2026" (drop leading zero)."""
    if not start:
        return None
    try:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt.strftime("%d %b %Y").lstrip("0")


def _description(pub: dict) -> str:
    """Build a share description from PUBLIC fields only (format · date · where)."""
    parts: list[str] = []
    if fmt := pub.get("format"):
        parts.append(str(fmt))
    if date := _format_date(pub.get("start")):
        parts.append(date)
    if pub.get("online"):
        parts.append("Online")
    elif country := pub.get("country"):
        parts.append(str(country))
    return " · ".join(parts) or SITE_DESCRIPTION


def _league_description(pub: dict, event_count: int) -> str:
    """League share description: kind/format · where · when · size, then blurb."""
    parts: list[str] = []
    if pub.get("kind") == "Meta-League":
        parts.append("Meta-League")
    if fmt := pub.get("format"):
        parts.append(str(fmt))
    if country := pub.get("country"):
        parts.append(str(country))
    start = _format_date(pub.get("start"))
    finish = _format_date(pub.get("finish"))
    if start and finish:
        parts.append(f"{start} – {finish}")
    elif start:
        parts.append(f"from {start}")
    if event_count:
        parts.append(f"{event_count} event{'s' if event_count != 1 else ''}")
    teaser = " · ".join(parts)
    blurb = str(pub.get("description") or "").strip()
    if blurb:
        if len(blurb) > 140:
            blurb = blurb[:139].rstrip() + "…"
        teaser = f"{teaser} — {blurb}" if teaser else blurb
    return teaser or SITE_DESCRIPTION


def _render_stub(
    base_url: str,
    canonical_path: str,
    title: str,
    description: str,
    banner: str | None,
) -> str:
    """Render the og-tagged HTML stub shared by all object types."""
    canonical = f"{base_url}{canonical_path}"
    beta = _is_beta(base_url)
    fallback = BETA_FALLBACK_IMAGE if beta else FALLBACK_IMAGE
    if banner:
        image, img_w, img_h = f"{base_url}{banner}", BANNER_W, BANNER_H
        card = "summary_large_image"
    else:
        image, img_w, img_h = f"{base_url}{fallback}", ICON_W, ICON_H
        card = "summary"
    # A banner makes the card indistinguishable from production otherwise, and the
    # results of an event recorded on beta never reach VEKN.
    if beta and not title.endswith(BETA_SITE_TITLE):
        title = f"{title} — {BETA_SITE_TITLE}"

    def e(s: object) -> str:
        return html.escape(str(s), quote=True)

    # No JS redirect: a misfiring browser would loop on location.replace back to
    # this same UA-split path. Crawlers read <head> only; the body is a courtesy.
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{e(title)}</title>
<link rel="canonical" href="{e(canonical)}" />
<meta property="og:type" content="website" />
<meta property="og:url" content="{e(canonical)}" />
<meta property="og:title" content="{e(title)}" />
<meta property="og:description" content="{e(description)}" />
<meta property="og:image" content="{e(image)}" />
<meta property="og:image:width" content="{img_w}" />
<meta property="og:image:height" content="{img_h}" />
<meta property="og:image:alt" content="{e(title)}" />
<meta name="twitter:card" content="{card}" />
<meta name="twitter:title" content="{e(title)}" />
<meta name="twitter:description" content="{e(description)}" />
<meta name="twitter:image" content="{e(image)}" />
</head>
<body><h1>{e(title)}</h1><p>{e(description)}</p></body>
</html>
"""


def render_site_og_html(base_url: str) -> str:
    """Site card for the bare app link — the form pasted to say "try the beta"."""
    return _render_stub(base_url, "/", _site_title(base_url), SITE_DESCRIPTION, None)


def render_og_html(base_url: str, uid: str, pub: dict | None) -> str:
    """`base_url` must be absolute (scheme://host) — og:image requires it for
    crawlers. `pub` is None or deleted → site-wide card, never an error."""
    title, description, banner = _site_title(base_url), SITE_DESCRIPTION, None
    # Both stubs canonicalise on the short form where there is one, so the two
    # URLs for the same event do not read as two pages.
    path = f"/tournaments/{uid}"
    if pub and not pub.get("deleted_at"):
        title = pub.get("name") or _site_title(base_url)
        description = _description(pub)
        banner = pub.get("banner_path")
        if pub.get("event_code"):
            path = f"/t/{pub['event_code']}"
    return _render_stub(base_url, path, title, description, banner)


def render_league_og_html(
    base_url: str, uid: str, pub: dict | None, event_count: int = 0
) -> str:
    """Render the og-tagged HTML stub for /leagues/{uid}.

    Leagues carry no banner — always the square site icon summary card.
    """
    title, description = _site_title(base_url), SITE_DESCRIPTION
    if pub and not pub.get("deleted_at"):
        title = pub.get("name") or _site_title(base_url)
        description = _league_description(pub, event_count)
    return _render_stub(base_url, f"/leagues/{uid}", title, description, None)


# Mirrors helpDocs in frontend/src/lib/help-docs.ts — keep both in sync.
# Crawlers get one language, so only base-locale strings live here.
HELP_PAGES: dict[str, tuple[str, str]] = {
    "rules": (
        "VTES Comprehensive Rules",
        "The complete official rules for Vampire: The Eternal Struggle.",
    ),
    "tournament-rules": (
        "Tournament Rules",
        "Official VEKN tournament rules and procedures.",
    ),
    "judges-guide": (
        "Judges Guide",
        "Tournament conduct and infraction guide for judges.",
    ),
    "code-of-ethics": (
        "Code of Ethics",
        "VEKN Code of Ethics for players and organizers.",
    ),
    "player-guide": (
        "Player Guide",
        "How to find tournaments, register, check in, and upload decks.",
    ),
    "organizer-guide": (
        "Organizer Guide",
        "How to create, configure, and run tournaments with Archon.",
    ),
}


def render_help_og_html(base_url: str, slug: str) -> str:
    """Render the og-tagged HTML stub for /help/{slug}."""
    page = HELP_PAGES.get(slug)
    if not page:
        return _render_stub(
            base_url, f"/help/{slug}", _site_title(base_url), SITE_DESCRIPTION, None
        )
    title, description = page
    return _render_stub(
        base_url,
        f"/help/{slug}",
        f"{title} - {_site_title(base_url)}",
        description,
        None,
    )
