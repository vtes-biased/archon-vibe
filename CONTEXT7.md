# Context7 Library Reference

Quick reference for up-to-date documentation via Context7 MCP.

## Frontend

| Library | Context7 ID | Snippets | Score |
|---------|-------------|----------|-------|
| **Svelte 5** | `/websites/svelte_dev` | 5,523 | 91.0 |
| **Vite** | `/vitejs/vite` | 1,011 | 76.9 |
| **TypeScript** | `/websites/typescriptlang` | 2,391 | 91.3 |
| **Tailwind CSS v4** | `/websites/tailwindcss` | 2,691 | 85.9 |
| **Playwright** | `/websites/devdocs_io_playwright` | 4,023 | 84.4 |

## Backend

| Library | Context7 ID | Snippets | Score |
|---------|-------------|----------|-------|
| **FastAPI** | `/websites/fastapi_tiangolo` | 12,277 | 96.8 |
| **msgspec** | `/jcrist/msgspec` | 172 | 92.3 |
| **psycopg 3** | `/websites/psycopg_psycopg3` | 949 | 81.8 |
| **pytest** | `/pytest-dev/pytest` | 1,053 | 87.7 |

## Engine (Rust)

| Library | Context7 ID | Snippets | Score |
|---------|-------------|----------|-------|
| **PyO3** | `/pyo3/pyo3` | 1,022 | 87.1 |
| **wasm-bindgen** | `/rustwasm/wasm-bindgen` | 325 | 88.6 |

## Web Standards (MDN)

| Library | Context7 ID | Snippets | Score |
|---------|-------------|----------|-------|
| **MDN Web Docs** | `/mdn/content` | 46,626 | 92.3 |

Use for: IndexedDB, Web APIs, JavaScript, HTML, CSS, Service Workers, etc.

## Usage

```
mcp__context7__query-docs with:
  libraryId: "/websites/fastapi_tiangolo"
  query: "SSE streaming response"
```

## Notes

- IDs chosen for best combination of snippet count + benchmark score
- Svelte 5 runes (`$state`, `$derived`) available in `/websites/svelte_dev`
- FastAPI official docs have best coverage (12k+ snippets)
- MDN covers IndexedDB, Service Workers, and all Web APIs (46k+ snippets)
