import { helpDocs } from '$lib/help-docs';

// Without entries() the prerender crawler cannot discover the slugs, so these
// routes were reported as "marked prerenderable but not prerendered" and fell
// back to 200.html. No load(): an unknown slug is already redirected to /help
// by the page itself.
export const entries = () => Object.keys(helpDocs).map((slug) => ({ slug }));
