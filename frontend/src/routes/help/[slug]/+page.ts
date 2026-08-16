import { helpDocs } from '$lib/help-docs';

// entries() lets the prerender crawler discover slugs, or these routes fall back
// to 200.html. No load(): an unknown slug is redirected to /help by the page itself.
export const entries = () => Object.keys(helpDocs).map((slug) => ({ slug }));
