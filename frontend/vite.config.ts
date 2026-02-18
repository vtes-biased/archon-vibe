import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { paraglideVitePlugin } from '@inlang/paraglide-js';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		tailwindcss(),
		paraglideVitePlugin({
			project: './project.inlang',
			outdir: './src/lib/paraglide',
			strategy: ['cookie', 'preferredLanguage', 'baseLocale'],
		}),
		sveltekit(),
	],
	server: {
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
		sourcemap: true,
		// Enable code splitting for large JSON imports
		rollupOptions: {
			output: {
				manualChunks(id) {
					// Split large cities.json into separate chunk
					if (id.includes('cities.json')) {
						return 'geonames-cities';
					}
					// Bundle help/reference docs separately to avoid bloating main chunk
					if (id.includes('judges-guide') || id.includes('tournament-rules') || id.includes('vtes-rules') || id.includes('code-of-ethics') || id.includes('help-content') || id.includes('help-docs')) {
						return 'help-docs';
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
