"""Guardrail: no frontend SPA page route may be shadowed by a backend-proxied
nginx prefix.

Frontend and backend share one origin behind nginx, split by path prefix: a
fixed set of prefixes proxies to the backend, everything else falls through to
the SPA shell. A frontend *page* placed under a backend prefix is therefore
sent to the API and 404s instead of booting the client router — this bit us
twice (/oauth/consent, /auth/email/verify, since relocated to /consent and
/verify-email).

This test reads the proxied-prefix list straight from the `static_site` role
default (the same source nginx renders from), so the guardrail and the deployed
config can't drift, and scans the real SvelteKit route tree. One invariant:
every page route lives outside every backend prefix.
"""

from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[2]
_ROUTES = _REPO / "frontend" / "src" / "routes"
_STATIC_SITE_DEFAULTS = (
    _REPO / "ansible" / "roles" / "static_site" / "defaults" / "main.yml"
)


def _backend_prefixes() -> list[str]:
    data = yaml.safe_load(_STATIC_SITE_DEFAULTS.read_text())
    prefixes = list(data["static_site_backend_paths_default"])
    prefixes.append(data["static_site_sse_path_default"])
    return prefixes


def _page_routes() -> list[str]:
    """URL path of every SvelteKit page, dropping (group) segments."""
    routes = []
    for page in _ROUTES.rglob("+page.svelte"):
        segs = [
            s
            for s in page.parent.relative_to(_ROUTES).parts
            if not (s.startswith("(") and s.endswith(")"))
        ]
        routes.append("/" + "/".join(segs))
    return routes


def _shadowed_by(route: str, prefix: str) -> bool:
    return route == prefix or route.startswith(prefix + "/")


def test_no_frontend_route_shadowed_by_backend_prefix() -> None:
    prefixes = _backend_prefixes()
    offenders = {
        route: prefix
        for route in _page_routes()
        for prefix in prefixes
        if _shadowed_by(route, prefix)
    }
    assert not offenders, (
        "Frontend page routes shadowed by a backend nginx prefix — these would "
        f"404 against the API instead of booting the SPA: {offenders}. Move the "
        "page out of the backend namespace (give it a frontend-only path)."
    )
