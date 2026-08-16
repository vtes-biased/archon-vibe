// Mirrors prod nginx, except a missing /_app/* asset 404s instead of falling
// back to 200.html — nginx masks that as a 200 HTML page, which is how
// asset-path regressions ship green; the 404 here is what catches them.
import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { join, extname, normalize } from 'node:path';

const ROOT = process.argv[2] || 'build';
const PORT = Number(process.env.SMOKE_PORT || 4173);
const FALLBACK = join(ROOT, '200.html');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.wasm': 'application/wasm',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.webmanifest': 'application/manifest+json',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
};

// Proxied to the backend in prod; there is none here, so 503 immediately rather
// than SPA-falling these to 200.html, which would feed HTML to fetch()/EventSource.
const API_PREFIXES = ['/api/', '/auth/', '/oauth/', '/vekn/', '/sanctions/', '/admin/', '/snapshot', '/stream'];

const server = http.createServer(async (req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);

  if (API_PREFIXES.some((p) => path === p || path.startsWith(p))) {
    res.writeHead(503).end('no backend in build smoke');
    return;
  }

  const rel = normalize(path).replace(/^(\.\.[/\\])+/, '');
  const file = join(ROOT, rel);
  try {
    if ((await stat(file)).isFile()) {
      res.writeHead(200, { 'content-type': MIME[extname(file)] || 'application/octet-stream' });
      res.end(await readFile(file));
      return;
    }
  } catch {
    /* not a readable file */
  }

  if (path.startsWith('/_app/')) {
    res.writeHead(404).end('not found');
    return;
  }

  res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
  res.end(await readFile(FALLBACK));
});

server.listen(PORT, () => console.log(`build smoke server: http://localhost:${PORT} serving ${ROOT}`));
