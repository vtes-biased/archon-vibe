import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { paraglideVitePlugin } from '@inlang/paraglide-js';
import { defineConfig } from 'vite';

export default defineConfig({
	// Build-time app version. CI (release-artifacts.yml) sets PUBLIC_APP_VERSION
	// from the git tag — the same single source as the backend/bot wheels; dev and
	// Docker builds (no env) show 'dev'.
	define: {
		__APP_VERSION__: JSON.stringify(process.env.PUBLIC_APP_VERSION ?? 'dev')
	},
	plugins: [
		tailwindcss(),
		paraglideVitePlugin({
			project: './project.inlang',
			outdir: './src/lib/paraglide',
			strategy: ['cookie', 'preferredLanguage', 'baseLocale'],
		}),
		sveltekit({
			preprocess: vitePreprocess(),
			adapter: adapter({
				pages: 'build',
				assets: 'build',
				fallback: '200.html',
				precompress: false,
				strict: true
			}),
			prerender: { handleHttpError: 'warn', handleUnseenRoutes: 'warn' },
			paths: {
				// Keep default true: false makes Vite 8 emit "./_app/immutable/..."
				// preload deps resolved against the entry chunk, doubling the path → 404.
				// The 200.html fallback uses absolute asset paths regardless of this.
				relative: true
			}
		})
	],
	server: {
		watch: {
			// A `build` while `dev` is live fired one page reload per emitted file;
			// reloading mid-flight strands initAuth and reads as a logged-out session.
			ignored: ['**/build/**', '**/.svelte-kit/output/**']
		},
		proxy: {
			'/api': {
				target: 'http://localhost:8000',
				changeOrigin: true
			}
		},
		fs: {
			// Allow serving files from engine/pkg (WASM)
			allow: ['..']
		}
	},
	build: {
		target: 'esnext',
		sourcemap: true
	},
	environments: {
		// Client only: the service worker environment inherits top-level build options and
		// must stay a single chunk.
		client: {
			build: {
				rolldownOptions: {
					output: {
						manualChunks(id) {
							if (id.includes('cities.json')) {
								return 'geonames-cities';
							}
							if (id.includes('judges-guide') || id.includes('tournament-rules') || id.includes('vtes-rules') || id.includes('code-of-ethics') || id.includes('help-content') || id.includes('help-docs')) {
								return 'help-docs';
							}
						}
					}
				}
			}
		}
	},
	// Enable JSON imports
	json: {
		stringify: false
	}
});
