"""Server-rendered Open Graph stub for shared tournament links.

Social link-preview crawlers (Discord, Facebook, Reddit, WhatsApp, …) don't run
JavaScript, so the SPA's client-set <meta> tags are invisible to them — every
share would fall back to the static app.html site-wide card. nginx UA-splits
``/tournaments/{uid}``: humans get the static SPA shell, crawlers are proxied to
the route that renders this HTML with per-tournament og:title/description/image.

Pure render here (no request/db); the route in main.py supplies the public-level
projection dict so this stays unit-testable and can't over-expose member fields.
"""

import html
from datetime import datetime

SITE_TITLE = "Archon"
SITE_DESCRIPTION = "VEKN Tournament Management - Web App"
FALLBACK_IMAGE = "/icon-512.png"  # square site icon
# Banner is the de-facto universal og:image size (see .pst/details/278).
BANNER_W, BANNER_H = 1200, 630
ICON_W, ICON_H = 512, 512


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


def render_og_html(base_url: str, uid: str, pub: dict | None) -> str:
    """Render the og-tagged HTML stub for /tournaments/{uid}.

    `base_url` is the absolute origin (scheme://host) — og:image MUST be absolute
    for crawlers. `pub` is the tournament's public projection (or None / deleted →
    site-wide card, never an error). A banner yields a large card; the square
    fallback icon a summary card.
    """
    canonical = f"{base_url}/tournaments/{uid}"
    title, description, banner = SITE_TITLE, SITE_DESCRIPTION, None
    if pub and not pub.get("deleted_at"):
        title = pub.get("name") or SITE_TITLE
        description = _description(pub)
        banner = pub.get("banner_path")

    if banner:
        image, img_w, img_h = f"{base_url}{banner}", BANNER_W, BANNER_H
        card = "summary_large_image"
    else:
        image, img_w, img_h = f"{base_url}{FALLBACK_IMAGE}", ICON_W, ICON_H
        card = "summary"

    def e(s: object) -> str:
        return html.escape(str(s), quote=True)

    # No JS redirect: in the UA-split (single canonical URL) a misfiring browser
    # would loop on location.replace back to this same path. Crawlers read <head>
    # only; the body is a courtesy for the rare human who reaches the stub.
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
