# 278 — Per-tournament banner / social-share image

> **Status:** Phase 1 shipped (upload + 1.91:1 cropper + in-app masthead hero +
> versioned `banner_path` at public level + the avatar-consistency versioned-URL
> fix). **Phase 2 shipped (#286)** — nginx UA-split + FastAPI OG stub +
> `og.py` render + `app.html` site-wide og tags + safe-zone overlay in the cropper.
> Design notes (Option A/B, nginx UA-split, gotchas) stay below as the reference.

Let organizers upload one image per tournament. It serves **two** jobs from a
single asset:

1. **In-app hero/header** for the tournament page (and cards/lists).
2. **Social-share `og:image`** when the tournament link is pasted into Discord,
   Facebook, Reddit, X, etc.

## Banner vs image — recommendation

One **banner**, not a gallery, not separate crops. A single landscape asset
covers both jobs and keeps the organizer UX to one upload + one crop.

## Dimensions (what to tell organizers + enforce in the cropper)

- **1200 × 630 px, aspect ratio 1.91:1.** This is the de-facto universal
  `og:image` size — renders correctly on Facebook, X (large card), LinkedIn,
  Slack, **Discord, and Reddit** from one file. Targeting any one platform's
  bespoke size breaks the others; 1.91:1 is the one-size-fits-all.
- **Safe zone ~1080 × 565 px, centered** (~60 px breathing room each side) —
  keep the tournament name / logo inside it; some surfaces crop edges or round
  corners.
- Format: PNG/JPEG are the safe `og:image` formats; WebP is fine for the
  in-app render and is what the avatar flow already accepts. Cap ≈1 MB (well
  under Facebook's 8 MB / practical 5 MB limit) — mirror the avatar cap.
- **Lock the client-side cropper to 1.91:1** so organizers can't ship an
  off-ratio image. (Avatar flow already does client crop → upload; reuse it.)

## Build on the existing AVATAR pattern (don't invent storage)

Avatars already prove the whole shape — copy it:

- `backend/src/db.py:1113+` — `avatars` table stores `(data bytes, content_type,
  updated_at)`, **separate from the `objects` table**; `upsert_avatar` /
  `get_avatar` / `delete_avatar`.
- `backend/src/routes/users.py:310-401` — `POST/GET/DELETE /api/users/{uid}/avatar`,
  `MAX_AVATAR_SIZE = 1MB`, accepts `webp/png/jpeg`, "client should resize/crop
  before upload", sets `avatar_path = /api/users/{uid}/avatar` on the object.
- `backend/src/models.py:288` — `avatar_path` field on the user.

Banner = the same, scoped to tournaments: a `banners` table (or generic asset
table), `banner_path` on the Tournament object, organizer-gated
`POST/GET/DELETE /api/tournaments/{uid}/banner`, served from the backend. The
in-app hero just reads `banner_path` from IndexedDB (offline-first reads
unaffected).

## Phase 1 — upload + in-app banner (works on current stack)

Storage + endpoint (avatar clone) → `banner_path` on Tournament (Rust model +
access projections; banner is presumably `public`-level so it shows pre-login)
→ organizer upload UI with 1.91:1 cropper → render hero on the tournament page.
No architecture changes needed.

## Phase 2 — banner as `og:image` (shipped #286 — Option B: nginx UA-split)

The hard part, and the reason this isn't trivial:

- Frontend is **`adapter-static` with a `200.html` SPA fallback**
  (`frontend/svelte.config.*`). Every route serves the **same** static HTML with
  **hardcoded** og tags pointing at `/icon-512.png`
  (`frontend/src/app.html:11-21`).
- **Social crawlers (Discord, Facebook, Reddit, X, Slack, WhatsApp) do not
  execute JavaScript.** So client-side updating of `og:image` per tournament is
  invisible to them — they only ever see the static `200.html` tags.

To make a tournament's banner the share image you need **server-rendered** meta
for the share URL.

### Per-platform display reality (2026, verified)

`1200×630` (1.91:1) is confirmed the correct **single** asset — every platform
reads one `og:image` tag and accepts this size, so multiple uploads / per-platform
crops are NOT worth it (OG can't serve a different image per platform anyway).
But *display* varies, and mobile is the worst case, so the asset must be designed
to survive cropping:

| Platform | Display of a 1.91:1 og:image | Crop |
| --- | --- | --- |
| **Discord** | scales the whole image into ~400×300, preserves aspect | none — shows it all |
| **Facebook** | large ~1.91:1 card on desktop; mobile feed placements go squarer | center-crops non-1.91:1 |
| **WhatsApp** | small left-hand thumbnail, heavily downscaled (small text unreadable) | center-crops to 1.91:1 |
| **Reddit** | tiny feed thumbnail (~140×100) | exact dims barely matter |
| **X** (not in scope) | prefers 16:9 `1200×675`; 1.91:1 still works | — |

Hard constraints this imposes on the Phase-2 / asset design:

- **Keep the title / key art in a centered safe zone (~1080×600).** Edges and
  top/bottom go first (square + mobile crops). This is the reason for safe-zone
  *guidance*, even though the in-app hero (Phase 1) shows the full image uncropped.
- **WhatsApp silently drops images over ~300 KB** (others allow 5–8 MB). Our
  cropper exports WebP @ q0.85 (~100–200 KB at 1200×630), comfortably under — but
  the backend `MAX_BANNER_SIZE = 1 MB` is more generous than WhatsApp tolerates,
  so a hand-uploaded near-1 MB PNG would lose its WhatsApp preview. Either keep
  relying on the cropper's WebP output or tighten the cap toward ~300 KB.
- **WebP is accepted** by WhatsApp/Discord/Facebook/Reddit link previews (2026),
  so the cropper's WebP output is fine for the og use too.

**Cropper guidance (shipped Phase 2):** centered dashed safe-zone overlay +
square "mobile crop" preview canvas in `BannerCropper.svelte`, so organizers see
what WhatsApp/mobile will actually show.

Sources: og-image.org, krumzi.com, ogrilla.com (WhatsApp), Meta WhatsApp
link-preview docs, opengraphplus.com (Discord), missinglinkz.io.

### Deployment lever (grounding)

nginx serves the static SPA from disk (`try_files $uri $uri.html /200.html`,
`ansible/roles/static_site/templates/https.conf.j2` + `frontend/nginx.conf`) and
reverse-proxies a **fixed list of path prefixes** (`/api /auth /oauth /vekn
/sanctions /admin /snapshot /stream`) to FastAPI, **same-origin** (load-bearing
for the `/snapshot X-Access-Version` handshake). So `/tournament/{uid}` is
served statically today and the backend never sees it. Any server-rendered og
route must either (a) live under a **new proxied prefix** routed to FastAPI, or
(b) be selected at nginx by User-Agent.

### GOTCHA: a 301/302 cannot carry og tags

A redirect response has a `Location` header and no body the crawler parses.
Facebook / Discord / Reddit / X **follow the redirect and read og tags from the
final destination** — so `301 /t/{uid} → /tournament/{uid}` lands them on the
static shell with the generic hardcoded tags and *destroys* the per-tournament
tags. You cannot have og-tags-and-redirect via an HTTP redirect.

Instead, serve a `200 OK` page carrying the per-tournament tags. The `<script>`
redirect line is needed ONLY for the separate-URL Option A; Option B (preferred)
serves the bot directly on the canonical URL and omits it.

```html
<!-- GET /t/{uid} -->
<meta property="og:title"       content="{tournament name}">
<meta property="og:description" content="{date · venue · format}">
<meta property="og:image"       content="{banner_path or /icon-512.png}">
<meta name="twitter:card"       content="summary_large_image">
<link rel="canonical" href="/tournament/{uid}">
<script>location.replace('/tournament/{uid}')</script>  <!-- humans only -->
```

Crawlers don't run JS / ignore meta-refresh → they stay and read the tags.
Browsers run the JS → bounce into the SPA. Use `location.replace` (not
`assign`) so the interstitial stays out of back-button history; `rel=canonical`
expresses the "permanent" intent to search engines (that's where "permanent"
lives — NOT an HTTP 301).

### Option B — one URL `/tournament/{uid}`, UA-split at nginx (PREFERRED)

Preferred because it satisfies both stated constraints: **offline stays intact**
(humans hit `try_files` → static shell → SW-cacheable; crawlers never run the
SW) and **address-bar copy Just Works for everyone** (one clean canonical URL,
no Share button required). Since the bot is already ON the canonical URL, **no
redirect is needed** — the backend returns `200` + per-tournament og tags
directly. (The Option-A client-redirect dance is only needed for a *separate*
`/t/` URL.)

nginx — use a named location, NOT `if { proxy_pass }` ("if is evil"):

```nginx
map $http_user_agent $is_social_bot {
    default 0;
    "~*facebookexternalhit|Facebot|meta-externalagent|Twitterbot|Discordbot|redditbot|Slackbot|Slack-ImgProxy|TelegramBot|WhatsApp|LinkedInBot|Pinterest|SkypeUriPreview|vkShare|Embedly|Iframely|FlipboardProxy|Bluesky|Mastodon|Applebot" 1;
}

location ~ ^/tournament/[0-9a-fA-F-]+$ {
    error_page 418 = @og_stub;
    if ($is_social_bot) { return 418; }   # internal hop only
    try_files $uri $uri.html /200.html;    # humans → static SPA
}
location @og_stub { proxy_pass http://127.0.0.1:{{ r.backend_port }}; }
```

Backend renders `200` HTML with og tags from `banner_path` for the carried
`/tournament/{uid}` path (add the prefix to `_backend_paths` or rely on the
named-location proxy).

UA list curated to **link-preview** crawlers (ground truth:
`github.com/monperrus/crawler-user-agents`). The three that matter here:
Discord=`Discordbot`, Facebook=`facebookexternalhit` (+`Facebot`,
`meta-externalagent`), Reddit=`redditbot` **and** `Embedly` (Reddit rich cards
proxy through Embedly).

Caveats:
- **Exclude search engines** (`Googlebot`/`Bingbot`) — they render JS and should
  index the real SPA route; the minimal og-stub would hurt indexing. Social
  preview only.
- **Drift degrades gracefully**: an unlisted new crawler just gets the generic
  site-wide card (today's behaviour), never an error — the list is maintenance,
  not a liability. Keep it in the `static_site` role so beta/prod stay in sync.

### Option A — separate `/t/{uid}` URL (fallback if UA-list upkeep unwanted)

The interstitial-with-client-redirect above (incl. the `<script>` line). Simpler
nginx, but needs an explicit **Share / Copy-link button** (+ mobile Web Share
API) — address-bar copy won't carry og — and `/t/` is a worse offline/SW route.
Use only if maintaining the UA list is undesirable.
- *Address-bar-copy variant:* `history.replaceState(null,'','/t/{uid}')` on
  detail-page mount makes the address bar show the share URL, but a hard refresh
  then double-bounces through the backend stub. Optional sugar.

### Global tags (do regardless)

Switch `twitter:card` from `summary` to `summary_large_image` for the landscape
banner, and add `og:image:width` / `og:image:height` / `og:image:alt` in
`frontend/src/app.html`.

## Scope note

Both phases shipped. Open consideration: moderation of organizer-uploaded public
images (banner is exposed at `public` access level).
