/**
 * Short-lived memory of where each list was left, so the nav menu returns the
 * viewer to their filtered view instead of the unfiltered default.
 *
 * The URL stays the single source of truth ($lib/url-filters): this only
 * decides which URL a bare nav link resolves to at click time. Nothing is ever
 * restored behind the viewer's back on a direct load, so a shared or bookmarked
 * link renders exactly what it says.
 *
 * sessionStorage, not localStorage: the memory dies with the tab, so a new tab
 * — including one opened from a shared link — always starts clean. A PWA tab
 * can live for days on mobile though, hence the inactivity window on top.
 */

import { goto } from "$app/navigation";

const STORAGE_KEY = "archon:last-view";
const TTL_MS = 30 * 60 * 1000;

/**
 * Not view preferences, so never carried into a list you re-enter from the
 * menu: a page number is a position and a search query is an intent, and a
 * restored one makes the list look broken. Back still restores both — it
 * replays the URL, which keeps them.
 */
const TRANSIENT = ["page", "q"];

interface Entry {
    search: string;
    at: number;
}

function load(): Record<string, Entry> {
    try {
        return JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "{}");
    } catch {
        return {};
    }
}

/** Record the view a list route was left in. */
export function rememberView(path: string, search: string): void {
    const params = new URLSearchParams(search);
    for (const key of TRANSIENT) params.delete(key);
    const kept = params.toString();
    const views = load();
    views[path] = { search: kept ? `?${kept}` : "", at: Date.now() };
    try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(views));
    } catch {
        // Private-mode quota: losing the memory only costs a default view.
    }
}

/**
 * The URL a link to `path` should open — the remembered view while it is fresh,
 * the bare route otherwise.
 */
function lastView(path: string): string {
    const entry = load()[path];
    if (!entry || Date.now() - entry.at > TTL_MS) return path;
    return path + entry.search;
}

/**
 * Click handler for a link back into a list: reopens it where the viewer left
 * it. Resolved here rather than baked into the href so it cannot go stale, and
 * so a modified click (new tab, new window) still gets the bare route — a fresh
 * tab should start on the default view.
 */
export function openLastView(event: MouseEvent, href: string): void {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const target = lastView(href);
    if (target === href) return;
    event.preventDefault();
    goto(target);
}

/** Drop every remembered view (on logout: filters can be role-dependent). */
export function forgetViews(): void {
    sessionStorage.removeItem(STORAGE_KEY);
}
