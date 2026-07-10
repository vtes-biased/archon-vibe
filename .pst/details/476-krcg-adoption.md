# EPIC #476 — adopt krcg (Python side) for card-DB build + deck URL providers

Self-contained so this can be worked after a context clear. Children: **#477**
(card-DB build, keystone), **#408** (deck URL providers via krcg + frontend
routing/offline gating — the reparented, broadened original Amaranth bug), **#478**
(optional TWDA import via krcg.twda, p3).

## Decisions locked with the owner (2026-07)

- **Adopt krcg** as a real backend dependency. It is the canonical VTES library and
  **owner-maintained**, so dependency risk is low for this project specifically.
- **Route ALL url-based deck imports through the backend** (not just Amaranth) via
  krcg providers, for consistency and because a URL fetch needs online anyway.
- **Disable url + QR deck import while offline.** QR is just a URL helper (a scanned
  QR that starts with `http` populates the URL field), so it follows the URL rule.
- **Raw-text decklist import must keep working offline** (frontend `parseDeckText`,
  which parses via the WASM engine — local, no backend, no krcg).
- **Keep the build-time bundled `cards.json` model** as the shipped default (see
  Open Decisions for the boot-refresh tension) — the offline-first PWA must ship the
  card DB into IndexedDB.
- `twda.py` (GitHub-App auto-PR to the TWD repo) is **not** a krcg overlap — keep it.
- Rust engine seating is Rust/WASM/offline — **not** replaceable by `krcg.seating`.

## Why this is bigger than the Amaranth bug (root cause)

The original #408 bug: `backend/src/providers.py:120-126` stores Amaranth's own card
IDs verbatim into `DeckObject.cards` as if they were VEKN IDs, so imported Amaranth
decks reference nonexistent cards. The frontend twin `deck-fetch.ts:159 fetchAmaranth`
has the identical gap.

Mapping Amaranth→VEKN correctly is hard and is exactly krcg's competency. Measured a
naive DIY matcher (our `cards.json` name index vs Amaranth's live catalog):

- **93.4% match** (4029/4313). Misses: **71 advanced vampires** (`… (ADV3)`) that
  *share the base card's name* so name-lookup collapses them onto the wrong (base)
  id; **~209 accent/ASCII** mismatches ("Francois"↔"François", "Zoe"↔"Zoé",
  "Lazar"↔"Lăzar"); **4 counters/tokens** (correctly skipped — not real cards).
- 93% silently mismaps advanced vampires and drops accented crypt cards — not
  shippable for a deck importer. A correct DIY matcher would re-derive krcg's
  accent-fold + alias + advanced-disambiguation logic.

Upstream `static.krcg.org/data/vtes.json` **already carries** what we need but our
build drops it — a card has `name` ("Alan Sovereign (G3 ADV)"), `_name` (base
"Alan Sovereign"), `name_variants`, and `adv: true`. Our `scripts/update_cards.py:
transform_card` collapses these (plain "Alan Sovereign", no adv, no ASCII variant),
which is the data-layer root of the match gap. Fixing the build fixes both stacks.

## Our current card-data pipeline (answer to "where do our cards come from")

- Source: **`static.krcg.org/data/vtes.json`** (same source krcg-the-lib uses).
- `scripts/update_cards.py` (`KRCG_BASE`, `transform_card`) → writes
  `engine/data/cards.json` (`OUTPUT`).
- Refresh = **build-time, not boot**: `.github/workflows/update-cards.yml` runs daily
  06:00 UTC, commits + tags `cards-<date>`, ships bundled in wheel + frontend build.
- Runtime: `backend/src/card_data.py` loads the bundled `cards.json` (env
  `CARDS_JSON_PATH` / package data / dev fallback), cached in-process. The frontend
  loads the same file into IndexedDB. The WASM engine also uses card data (text
  import + validation).

## The one hard architecture constraint

**krcg is Python.** The offline-first frontend (browser/TS) — `deck-fetch.ts`,
`parseDeckText`, the IndexedDB card DB, card display — **cannot import krcg**. So krcg
adoption is a **backend + build-script** consolidation only. Where the frontend needs
krcg-quality results (URL imports incl. Amaranth), it routes through the backend.

## krcg v5.5 API cheat-sheet (facts confirmed by introspection)

- PyPI latest **5.5**, `requires-python >=3.12` (fine — we pin 3.14).
- Deps pulled: **aiohttp, arrow, msgspec, numpy, pyyaml, unidecode** (backend already
  has aiohttp + msgspec; new: arrow, numpy, pyyaml, unidecode). numpy is a hard dep
  even if we only use providers.
- Load the card DB: **`from krcg import loader; cards = loader.load()`** →
  `krcg.collections.CardDict` (offline, packaged/pickled; `loader.load_online(session)`
  fetches fresh; `load_local(available)` too). `CardDict` supports name lookup
  (`cards[name]`) and id lookup.
- `krcg.providers` (all async, take an `aiohttp.ClientSession`):
  - `get_amaranth_cards_map(session, cards_dict) -> dict[str, Card]` — fetches
    Amaranth's `/api/cards` catalog and maps `amaranth_id -> Card` by matching names
    to `cards_dict` (skips storyline/counter cards not in the DB). Cache + reuse.
  - `fetch_amaranth(session, url, cards_dict, *, amaranth_map=None) -> models.Deck` —
    fetches the deck, maps each `{amaranth_id: count}` via `amaranth_map` to real
    `Card`s. Returns a `krcg.models.Deck`; extract `{card.id: count}` (VEKN ids).
  - There are VDB / VTESDecks equivalents in the same module — confirm exact names
    (`dir(krcg.providers)`) during impl.
- `krcg.models.Card.id` is the VEKN card id. `krcg.utils`: `normalize`, `vekn_name`,
  `add_card`, `sort_cards`, `FuzzyDict` — the resolution machinery.
- `krcg.parser.deck_from_txt`, `krcg.twda.load_online/fetch_from_source`,
  `krcg.vekn_csv.from_files/compute_variants` — for later children / reference.

## Inventory: hand-rolled vs krcg (what to replace, what to keep)

| Our code | krcg equiv | Action |
|---|---|---|
| `scripts/update_cards.py` (card build, 90 L) | card data + `compute_variants`/`normalize` | **Replace (#477)** |
| `backend/src/providers.py` (URL providers, 132 L) | `krcg.providers.*` | **Replace (#408)** |
| `frontend/src/lib/deck-fetch.ts` URL fetch (TS) | — | **Keep TS; route URL/QR via backend (#408)** |
| `frontend` `parseDeckText` (WASM, offline) | `krcg.parser` | **Keep (offline raw-text)** |
| `backend/src/twda_import.py` (198 L, JSON consumer) | `krcg.twda` | **Optional (#478, p3)** |
| `backend/src/twda.py` (GitHub-App auto-PR, 192 L) | — | **Keep** |
| Rust engine seating | `krcg.seating` | **Keep (Rust/WASM/offline)** |

## Per-child implementation plan

### #477 — card-DB build via krcg (keystone; do first)
- Rebuild `scripts/update_cards.py` to source card data from krcg (`loader.load()` or
  krcg's card model) so `engine/data/cards.json` carries: correct **ASCII names**,
  full **name_variants/aliases**, the **adv flag**, and the group/adv-suffixed names.
  Keep the SAME output shape the engine + frontend + `card_data.py` already consume,
  or update all three consumers in lockstep (schema change → engine cards parsing,
  frontend `cards.ts`/`types.ts`, `/api/cards`).
- This fixes card-name resolution for BOTH stacks (shared bundled file) and is what
  makes Amaranth mapping correct at the data layer.
- Verify: rerun the match spike — advanced + accented cards should now resolve.

### #408 — deck URL providers via krcg + frontend routing/offline gating
- **Backend** `providers.py`: replace the hand-rolled `_fetch_vdb`/`_fetch_vtesdecks`/
  `_fetch_amaranth` with krcg providers. `_fetch_amaranth` uses
  `get_amaranth_cards_map` (cache the map — it fetches Amaranth's whole catalog) +
  `fetch_amaranth`, returning `{vekn_id: count}`. Keep the `fetch_deck_from_url(url)
  -> {name,author,comments,cards}` signature the `/fetch-deck` proxy expects.
  - Integration gotcha: `fetch_deck_from_url` is sync, called via
    `asyncio.to_thread` (`tournaments.py:949`); krcg providers are async/aiohttp.
    Either `asyncio.run(...)` an aiohttp session inside the thread, OR make the
    provider path async and call it directly from the `/fetch-deck` endpoint
    (`tournaments.py:933`). Prefer making it async and dropping the `to_thread`.
  - Build the `CardDict` once (module-level, `loader.load()`), reuse across requests.
- **Frontend** `DeckUpload.svelte` (modes `'text'|'url'|'qr'`, line 26):
  - URL mode (`:143` `fetchDeckFromUrl(deckUrl)`) → call the backend
    `GET /fetch-deck?url=` proxy instead of the in-browser `deck-fetch.ts` fetch.
  - QR mode (`:85-91`) scans → sets `deckUrl` + switches to URL mode → same route.
  - **Disable url + qr mode toggles while offline** (buttons at `:217`, `:225`);
    locate the app's online/offline signal (offline_mode for tournaments + likely a
    connection store / `navigator.onLine`).
  - **Keep text mode** (`:135/:138` `parseDeckText` via WASM) working offline.
  - Optionally strip the now-unused URL branches from `deck-fetch.ts` (keep
    `parseDeckText`); or leave `deck-fetch.ts` URL code dead and just stop calling it.
- This is the original #408 fix (Amaranth ids → VEKN ids) plus the consistency route.

### #478 — TWDA import via krcg.twda (optional, p3)
- Consider replacing `twda_import.py`'s `static.krcg.org/data/twda.json` fetch with
  `krcg.twda.load_online(session)`. Overlap is modest (it's a thin JSON consumer +
  our own `DeckObject` mapping), so lowest priority. Keep `twda.py`.

## Open design decisions (settle during the epic)

1. **Card-DB refresh model — bundle vs boot-refresh.** Owner floated using krcg to
   refresh the card list on boot. Tension: the offline-first PWA MUST ship a bundled
   `cards.json` into IndexedDB, so build-time bundling stays regardless. If the
   backend *also* refreshes independently at boot/daily via krcg, backend and the
   bundled frontend card DB can diverge → validation inconsistency. Recommendation:
   keep the daily-CI bundled artifact as the single source; if backend refresh is
   wanted, gate it so it can't diverge from the shipped `cards.json` the frontend
   holds. Decide before #477 lands.
2. **cards.json schema change.** Adding `adv`/ASCII variants means touching every
   consumer (engine cards parsing, `/api/cards`, frontend `cards.ts`/`types.ts`,
   IndexedDB hydration). Scope this as part of #477.
3. **Confirm krcg's VDB/VTESDecks provider function names** (`dir(krcg.providers)`)
   before replacing those branches; VDB/VTESDecks already return VEKN ids, so the win
   there is consistency, not correctness — verify no regression.

## Key file references

- `backend/src/providers.py:104-132` (`_fetch_amaranth`), `:120-126` (the bug)
- `backend/src/routes/tournaments.py:933` (`GET /fetch-deck` proxy), `:946-949`
  (`fetch_deck_from_url` via `to_thread`)
- `frontend/src/lib/deck-fetch.ts:25` (`fetchDeckFromUrl`), `:69` (`parseDeckText`),
  `:159` (`fetchAmaranth`), `:39` (amaranth branch)
- `frontend/src/lib/components/DeckUpload.svelte:26` (mode), `:85-91` (QR→URL),
  `:135-143` (fetch/parse), `:217`/`:225` (url/qr toggles)
- `scripts/update_cards.py` (`KRCG_BASE`, `transform_card`, `OUTPUT`),
  `.github/workflows/update-cards.yml` (daily), `backend/src/card_data.py`
- Add the dep in `backend/pyproject.toml` (backend already has aiohttp + msgspec)
- Verification spike (throwaway): fetch `https://amaranth.vtes.co.nz/api/cards`,
  compare Amaranth names to `cards.json` name index → measure match rate before/after.

## PROGRESS + RESOLUTION (2026-07)

### #408 — DONE (commit 653c41c)
`providers.py` rewritten on krcg providers (Amaranth id→VEKN mapping fixed, the
core bug); `/fetch-deck` async; frontend routes all url/QR through the backend,
gates them offline, keeps raw-text local. krcg added as backend dep. i18n ×5 done.

### Findings that reshaped the epic
- The old "cards.json drops adv/name_variants" premise was **stale**: the shipped
  build already carried `adv`, `name_variants`, group/ADV-suffixed `name`. The one
  real data gap is **ASCII folding** (69–73 accented crypt names have no fold).
- Card *matching* lives in the **Rust engine** (offline text import; WASM can't call
  krcg). Measured: the engine already resolves ADV/group/accented names correctly;
  the only real gaps are (a) an **X-name count bug** and (b) **ASCII folding**.
- **X-name bug FIXED** (commit 3f9ad42, ticket #479): `try_count_first` greedily ate
  the count marker's `x`/`X` into the name, so every X-named crypt card failed.
- **krcg parser bug FIXED upstream** (`../krcg` commit 7c725d3): `(G3 ADV)`/`(G6)`
  parentheticals were stripped as comments → resolved to base/wrong group. Now kept.

### #477 — RESOLVED naming model (owner spec, 2026-07): three names + folding parser
cards.json replaces the single `name` with three krcg-sourced names (raw vtes.json
can't supply `unique_name` — it's a krcg computed property, so the build MUST use
`krcg.loader`):
- `printed_name` — bare (krcg `printed_name`) → **frontend display** (adv/group shown
  as separate badges, NOT baked into the displayed string).
- `unique_name` — krcg `unique_name` (minimal disambiguator; most vampires bare, later
  groups/advanced get the suffix) → **text decklist output** + a parse key.
- `full_name` — krcg `full_name` (always group/adv suffix) → a parse key.
Keep: kind, types, disciplines, clan, group, capacity, adv, banned, sets (names via
`CardDict.sets`), img (krcg `url`), name_variants (aliases/i18n — extra parse keys).

Parser: index printed+unique+full+variants; Rust `normalize_name` folds non-ASCII→ASCII
on BOTH index and query so accent-free typing matches (owner: "the parser folds
accents") — NOT baked as data folds.

Parser format coverage (owner, 2026-07): the Rust engine parser must handle **any**
decklist format, INCLUDING the TWDA-style crypt line where the group is at the END of
the line (after capacity/disciplines/clan/title — no group-in-parenthesis), e.g.
`2x Theo Bell   8 aus cel dom for pot pre  justicar  Brujah:6`. Study krcg's
`parser.py` + `tests/test_parser.py` (and the TWDA snapshot fixtures) and match its
capability. The engine already has `parse_crypt_tail_group`/`try_strip_crypt_tail` —
audit vs krcg for gaps.

Badge display (owner, 2026-07):
- ADV → the **advanced icon from the krcg/VTES icon font** (not the text "ADV"). Find
  the font used by krcg-static / the existing frontend discipline+clan icons.
- Group → a **circled number** (①②③…); group **"any"** (e.g. group-independent /
  merged crypt) gets **no** badge.

Migration (lockstep — no red build): (1) `update_cards.py` → krcg loader → new schema;
(2) engine `cards.rs` Card struct + name_index over the three names + ascii-folding
`normalize_name`, `deck.rs` text export via `unique_name` (V5 check keeps set names);
(3) frontend `VtesCard` + display printed_name + adv/group badges (CardSearch:64,
DeckDisplay, PlayerDecksSection); (4) backend `/api/cards` passthrough; (5) i18n badges.
Open micro-decisions during impl: transitional `name` alias?; V5 check via krcg
`formats` vs set-name strings; the Rust fold impl (cover ł/ø/æ beyond NFD).
Agents to consult: principal-engineer (Rust/WASM + data-model), staff-frontend-engineer
(badge display), product-manager (naming/display UX), senior-qa.

### #478 — evaluated, NO CHANGE (keep twda_import.py)
krcg.twda would replace only a ~18-line crypt/library flatten with **no correctness
gain**: `static.krcg.org/data/twda.json` already carries resolved VEKN card ids (unlike
the providers/parser, where krcg's *resolution* fixed real bugs). Against that, switching
to `krcg.twda.load_online` (a) **drops the ETag 304 optimization** (it unconditionally
refetches + parses ~12MB / 4.5k Deck objects each run) and (b) **doesn't expose the VEKN
event id** the import matches on — krcg's `Deck.event` has no `id`, and its `url` varies
(recent entries link to `archon.vekn.net/tournament/<uuid>`), so `_extract_vekn_event_id`
would have to be re-derived. Not worth it. `twda.py` (GitHub-App auto-PR) was never a
krcg overlap — kept.

### Spun-off fixes (found during the epic, fixed separately)
- **#479** — deck text-parse dropped X-named crypt cards (count parser ate the leading x).
- **#480** — V5-legality now a precomputed `cards.json` flag (VEKN §6.4 set allowlist +
  Format.V5 promo whitelist), replacing the broken `starts_with("V5")` set-name check.
- **upstream ../krcg** — parser now keeps `(G3 ADV)`/`(G6)` group/adv parentheticals
  (were stripped as comments → resolved to base/wrong group).
