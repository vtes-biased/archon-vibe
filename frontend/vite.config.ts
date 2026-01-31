import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
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
				}
			}
		}
	},
	// Enable JSON imports
	json: {
		stringify: false
	}
});
