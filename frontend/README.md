# Frontend

Svelte + Vite + TypeScript frontend for the offline-first PWA.

## Stack

- **Framework**: Svelte 5
- **Build Tool**: Vite 7
- **Language**: TypeScript
- **Styling**: Tailwind CSS 3
- **Local Storage**: IndexedDB (via `idb`)
- **PWA**: Service workers (to be configured)

## Development

```bash
# Install dependencies
npm install

# Run dev server (http://localhost:5173)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Structure

```
src/
├── App.svelte          # Main app component
├── main.ts             # Entry point
├── types.ts            # TypeScript type definitions (sync with backend)
├── lib/
│   └── db.ts          # IndexedDB setup and utilities
├── style.css          # Global styles
└── vite-env.d.ts      # Type definitions for Svelte
```

## Features

- **Online/Offline Detection**: App shows connection status
- **IndexedDB Storage**: Local data persistence
- **Change Log**: Tracks offline changes for sync
- **Type Safety**: Shared types with backend
- **API Proxy**: `/api` routes proxy to backend at `localhost:8000`

## Configuration

- `vite.config.ts`: Vite and plugin configuration
- `svelte.config.js`: Svelte preprocessing
- `tsconfig.json`: TypeScript configuration
- `tailwind.config.js`: Tailwind CSS configuration
- `postcss.config.js`: PostCSS with Tailwind and Autoprefixer

## Type Synchronization

Keep `src/types.ts` synchronized with `backend/src/models.py` using the `python-to-typescript-models` rule.

