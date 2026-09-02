// sessionStorage, not localStorage: a PWA tab can live for days on mobile, so the 30-min inactivity
// window (TTL_MS) matters — a fresh or stale tab always starts clean.

import { goto } from "$app/navigation";

const STORAGE_KEY = "archon:last-view";
const TTL_MS = 30 * 60 * 1000;

/** Dropped from the remembered view — a position or an arrival intent, not a view preference. Back still restores them via the URL. */
const TRANSIENT = ["page", "q", "sponsor"];

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

/** The URL a link to `path` should open — the remembered view while fresh, the bare route otherwise. */
export function lastView(path: string): string {
    const entry = load()[path];
    if (!entry || Date.now() - entry.at > TTL_MS) return path;
    return path + entry.search;
}

/** Reopens a list link where the viewer left it. Resolved here rather than baked into the href so it
 * can't go stale, and a modified click (new tab/window) still gets the bare route. */
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
