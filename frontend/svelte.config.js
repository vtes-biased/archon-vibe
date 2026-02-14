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
		paths: {
			relative: false
		},
		alias: {
			$lib: 'src/lib',
			$components: 'src/lib/components',
			$engine: '../engine/pkg'
		}
	}
};

export default config;
