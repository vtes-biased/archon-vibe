import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({
			pages: 'build',
			assets: 'build',
			fallback: '200.html', // SPA fallback for client-side routing
			precompress: false,
			strict: true
		}),
		prerender: {
			handleHttpError: 'warn',
			handleUnseenRoutes: 'warn'
		},
		paths: {
			// Keep default true: false makes Vite 8 emit "./_app/immutable/..."
			// preload deps resolved against the entry chunk, doubling the path → 404.
			// The 200.html fallback uses absolute asset paths regardless of this.
			relative: true
		},
		alias: {
			$lib: 'src/lib',
			$components: 'src/lib/components',
			$engine: '../engine/pkg'
		}
	}
};

export default config;
