# Third-party tournament scope

Doc-impact: `wiki/access.md` (scope semantics, the OAuth allowlist, consent
keying), `wiki/sync.md` (scoped-stream contract for third parties; the decks
read as a **delegated third-party read** — a new documented class, distinct
from the PWA's online-only-REST carve-out, or a future agent will "fix" it
away), `wiki/discord.md` (bot as first consumer of the real model),
`wiki/hazards.md` (the OAuth gate now lives in the middleware, the stream
handler's `_resolve_viewer` path *and* the public API's own token check —
the two-implementations-of-one-gate entry grows).

## Motivation

Integrating online-play platforms (JOL, Succubus Club): they impersonate an
organizer to read decklists once a round starts and to post tournament
actions. Today `user:impersonate` is all-or-nothing — the middleware denylist
blocks only `/auth/*` and `/admin/*`, so a token reaches users, promos, NDA
reads, account surgery, and (via `_resolve_viewer`) the **unscoped** `/stream`
and `/snapshot`: the organizer's whole corpus, private decks included. That
exposure is the correctness half of this line.

## Decisions (owner, 2026-08-27)

- **Per-tournament grants are the design, not a follow-up**: `/setup`
  authorizing an organizer once for all their events was never the intent.
  `user:impersonate` is granted per event; **unscoped impersonate tokens are
  dropped outright** — no legacy regime, they have no effective use today.
- **Sanctions stay third-party-issuable, issue-only**: allowlist
  `POST /sanctions/` (carrying the token's tournament) and
  `GET /sanctions/reference`; lift/modify/delete stay app-only. The bot's
  `/sanction` flow is attributed to the human judge and engine-gated by
  `issue_tournament_sanction`; DQ rides the same engine gate, no extra bar.
- **Decks are a REST pull, not a stream push.** The scoped stream's no-decks
  property is load-bearing (it is why scoped streams skip the access-version
  handshake), the stream serves stored projection columns and cannot retract
  a deck when a round ends, and a second stream endpoint would duplicate
  subtle machinery (shields, coalescing, participant refresh). The platform
  sees the round start on the scoped stream — the member projection already
  carries rounds and seating — and pulls the decks once.

## Shape

- Authorize request names the tournament (scope `tournament:<uid>` beside
  `user:impersonate`, surfaced as a claim); the consent page names the event
  to the user; consent keyed `(client, user, tournament)` — a returning user
  gets a one-click approve per new event, never a silent cross-event
  auto-approve. Players hold these tokens too (bot `/register`, `/checkin`,
  `/report`), so the one-click matters.
- `/oauth/authorize` refuses a grant on a `Finished` tournament and refresh
  dies once the event finishes — the structural answer to "no interacting
  with finished events". Bar `Reopen` for OAuth actors; the engine already
  state-gates everything else per action.
- Enforcement flips the middleware denylist to an allowlist for
  `oauth_access`: `/oauth/*`, the token's own tournament under
  `/api/tournaments/`, the sanctions pair above, `/stream` only with the
  matching `tournament=`. No unscoped stream, no `/snapshot`. The stream-side
  check cannot live in the path-based middleware gate alone.
- Barred infrastructure actions regardless of capability: tournament delete,
  go-offline / force-takeover / force-unlock / sync-offline, organizer
  add/remove, push-vekn, Reopen.
- `GET /api/tournaments/{uid}/decks`: full entitlement only (403 otherwise).
  Computes ongoing rounds (any round with a table `In Progress` — covers
  open/parallel rounds having several at once) and returns
  `rounds: [{round, decks}]` — per ongoing round, each seated player's deck:
  the round-numbered deck in multideck events (`DeckObject.round`), the
  registered deck otherwise, absent when not yet submitted. Empty when no
  round is ongoing. One uniform shape even for single-deck events.
- Bot: token store re-keyed per `(user, tournament)`; `/setup` mints a fresh
  per-event grant. Pre-production, so the re-keying is cheap now.

The already-boarded "Login with Archon" docs line absorbs documenting all of
this and should land after it.
