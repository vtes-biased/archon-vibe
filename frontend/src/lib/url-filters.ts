// Read from window.location, never the `page` store: replaceState is shallow routing, so a Back into
// a filtered entry hands the store the pre-filter URL while location holds the real one.

import { replaceState } from '$app/navigation';
import { rememberView } from '$lib/last-view';

/** Query params of the URL actually in the address bar. */
export function currentParams(): URLSearchParams {
    return new URL(window.location.href).searchParams;
}

/** History-neutral (Back must leave the list, not step through every filter change) and drops null/
 * empty params for a clean default URL. Feeds last-view's memory before the no-op check, so a view arrived at via shared link is remembered too. */
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
