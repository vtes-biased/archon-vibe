---
name: card-data-pipeline
description: Card DB and deck-URL-import now source from krcg (owner-maintained VTES lib), not hand-rolled parsing — two docs restate this flow and both drift.
metadata:
  type: project
---

Since epic #476 (2026-07, commits 653c41c/#408 and 9fe99d6/#477), two previously
hand-rolled pipelines were replaced with krcg (the canonical, owner-maintained VTES
Python library — a real backend dependency now):

- **Card DB build** (`scripts/update_cards.py`): sources via `krcg.loader.load_online`
  instead of hand-parsing raw `static.krcg.org/data/vtes.json`. Still build-time only
  (daily CI, bundled into wheel + frontend) — not a boot-time refresh; that tension was
  discussed and deliberately rejected (offline-first PWA must ship a bundled
  `cards.json`, and independent backend refresh risks backend/frontend divergence).
- **Deck URL import** (VDB/VTESDecks/Amaranth): routes through the backend
  `GET /fetch-deck` proxy using `krcg.providers`, which resolves provider-native card
  ids (notably Amaranth's own ids — the original bug) to VEKN ids against krcg's own
  bundled card DB, independent of our `cards.json`. QR is just a URL-scan shortcut into
  URL mode. Both URL and QR import are disabled while offline; raw-text paste stays
  local via the WASM engine (`parseDeckText`) and never touches krcg (krcg is Python —
  the frontend can't import it).

**Why this is a documentalist trap**: this flow is described in *two* places —
ARCHITECTURE.md's "Card/Deck System" section (detailed) and PRODUCT.md's "Decks"
feature bullet (terse restatement). When #476/#408 first landed, ARCHITECTURE.md kept
a stale line ("client fetches deck URLs directly; backend offers a CORS proxy
fallback") through a full prior commit before being caught — the CORS proxy is real,
but framed backwards: it's now the sole route, not a fallback behind direct client
fetch. Check both docs whenever this pipeline changes again — see [[card-data-pipeline]]
pointer in MEMORY.md's "Which Docs Update Together".

**VtesCard schema** (as of #477): the single `name` field is gone, replaced by
`printed_name`/`unique_name`/`full_name` (see MEMORY.md terminology note) — engine
`normalize_name` (`engine/src/cards.rs`) also folds Latin accents to ASCII on both the
index and the query as of this change.
