"""Guardrail: no frontend SPA page route may be shadowed by a backend-proxied
nginx prefix — a page under a backend prefix 404s against the API instead of
booting the SPA (bit us twice: /oauth/consent, /auth/email/verify, since
relocated). Reads the proxied-prefix list from `deploy/routes.py`, the same
source nginx renders from, so the check can't drift from the deployed config.
"""

import importlib.util
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[2]
_ROUTES = _REPO / "frontend" / "src" / "routes"


def _backend_prefixes() -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "routes", _REPO / "deploy" / "routes.py"
    )
    routes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routes)
    return [*routes.BACKEND_PATHS, routes.SSE_PATH]


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
    # production renders from the Ansible role until it moves to deploy/
    ansible = _REPO / "ansible" / "roles" / "static_site" / "defaults" / "main.yml"
    if ansible.exists():
        data = yaml.safe_load(ansible.read_text())
        assert [
            *data["static_site_backend_paths_default"],
            data["static_site_sse_path_default"],
        ] == prefixes, "deploy/routes.py and the static_site role disagree"
    assert not offenders, (
        "Frontend page routes shadowed by a backend nginx prefix — these would "
        f"404 against the API instead of booting the SPA: {offenders}. Move the "
        "page out of the backend namespace (give it a frontend-only path)."
    )
