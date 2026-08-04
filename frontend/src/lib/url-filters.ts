/**
 * Filter state in the address bar.
 *
 * List screens keep their filters and page number in the query string so that
 * leaving for a detail page and coming back restores the view (the component is
 * destroyed on navigation, local state is not), and so a filtered list can be
 * shared or bookmarked.
 *
 * Read from window.location, never from the `page` store: `replaceState` is
 * shallow routing, so it updates the history entry but not the store's memory
 * of it — a Back into a filtered entry hands the store the pre-filter URL while
 * location holds the real one. The app renders client-side only (ssr = false),
 * so location is always there at component init.
 */

import { replaceState } from '$app/navigation';
import { rememberView } from '$lib/last-view';

/** Query params of the URL actually in the address bar. */
export function currentParams(): URLSearchParams {
    return new URL(window.location.href).searchParams;
}

/**
 * Mirror the given params into the current URL. A null or empty value drops its
 * param, keeping default views on a clean URL. The write is history-neutral:
 * Back must leave the list, not step through every filter change.
 *
 * Also feeds the nav menu's short-lived memory ($lib/last-view) — before the
 * no-op check, so a view arrived at through a shared link is remembered too.
 */
export function syncQueryParams(params: Record<string, string | null>): void {
    const current = new URL(window.location.href);
    const next = new URL(current);
    for (const [key, value] of Object.entries(params)) {
        if (value === null || value === '') next.searchParams.delete(key);
        else next.searchParams.set(key, value);
    }
    rememberView(next.pathname, next.search);
    if (next.search === current.search) return;
    replaceState(next.pathname + next.search + next.hash, {});
}

/** Read the human-facing 1-based `page` param as a 0-based index. */
export function readPageParam(): number {
    const n = Number(currentParams().get('page'));
    return Number.isFinite(n) && n > 1 ? Math.floor(n) - 1 : 0;
}

/** Write the 0-based page index as a 1-based param, omitted on the first page. */
export function pageParam(page: number): string | null {
    return page > 0 ? String(page + 1) : null;
}
